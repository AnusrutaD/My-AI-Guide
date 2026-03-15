"""
Session Router — REST API for managing mentor sessions.

Endpoints:
  POST /session/start          → kick off a new session (runs to question)
  POST /session/respond        → submit code/answer (runs evaluator)
  GET  /session/{thread_id}    → fetch current state
  GET  /session/{thread_id}/history  → full message history
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.graph.state import DEFAULT_STATE
from app.services.clarifier import generate_clarification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/session", tags=["Session"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the learner")
    thread_id: str | None = Field(
        None,
        description="Existing thread ID to resume. Omit to create a new session.",
    )


class StartSessionResponse(BaseModel):
    thread_id: str
    question_text: str
    topic: str
    subtopic: str
    difficulty: str
    question_type: str = Field(
        default="CODING",
        description="CODING | SYSTEM_DESIGN | DEBUGGING",
    )
    test_cases: list[dict[str, str]] = Field(
        default_factory=list,
        description="For CODING: [{input, expected}] for run/submit",
    )


class RespondRequest(BaseModel):
    user_id: str
    thread_id: str
    response: str = Field(..., description="Code/design answer, or command: hint / skip / clarify:<question>")


class RespondResponse(BaseModel):
    feedback: str
    verdict: str
    score_delta: float
    next_action: str = "Reply to this message to start the next challenge."


class SessionStateResponse(BaseModel):
    thread_id: str
    interview_stage: str
    current_topic: str | None
    current_subtopic: str | None
    knowledge_gap_score: float | None
    messages: list[dict[str, Any]]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_graph(request: Request):
    graph = request.app.state.graph
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised — check server startup logs.")
    return graph


def _thread_config(thread_id: str, user_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id, "user_id": user_id}}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/start", response_model=StartSessionResponse)
async def start_session(body: StartSessionRequest, request: Request):
    """
    Launch a new mentor session (or resume one) for a user.
    Runs Strategist → Scraper → QuestionSetter and returns the question.
    """
    import uuid

    graph = _get_graph(request)
    thread_id = body.thread_id or str(uuid.uuid4())
    config = _thread_config(thread_id, body.user_id)

    initial_state: dict = {
        **DEFAULT_STATE,
        "user_id": body.user_id,
        "thread_id": thread_id,
        "interview_stage": "idle",
    }

    logger.info("[Session] Starting session thread_id=%s user_id=%s", thread_id, body.user_id)

    try:
        final_state = await graph.ainvoke(initial_state, config=config)
    except Exception as exc:
        logger.exception("[Session] Graph invocation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    question_text = final_state.get("question_text") or "No question generated — check logs."
    current_question = final_state.get("current_question") or {}
    test_cases = current_question.get("test_cases") or []
    question_type = current_question.get("question_type", "CODING")
    return StartSessionResponse(
        thread_id=thread_id,
        question_text=question_text,
        topic=final_state.get("current_topic", "Unknown"),
        subtopic=final_state.get("current_subtopic", "general"),
        difficulty=final_state.get("suggested_difficulty", "HARD"),
        question_type=question_type,
        test_cases=test_cases,
    )


@router.post("/respond", response_model=RespondResponse)
async def respond_to_question(body: RespondRequest, request: Request):
    """
    Submit a code / design response for evaluation.
    Resumes the graph at the Evaluator node.
    """
    graph = _get_graph(request)
    config = _thread_config(body.thread_id, body.user_id)

    # Special commands
    lower = body.response.strip().lower()
    if lower == "hint":
        state_snapshot = await graph.aget_state(config)
        question = (state_snapshot.values or {}).get("current_question", {})
        hints = question.get("hints", ["No hints available."])
        return RespondResponse(
            feedback="\n".join(f"• {h}" for h in hints),
            verdict="HINT",
            score_delta=0.0,
            next_action="Continue working on the problem or submit your solution.",
        )

    if lower == "skip":
        # Inject a skip marker and restart the pipeline
        await graph.aupdate_state(
            config,
            {"interview_stage": "idle", "user_response": "[SKIPPED]"},
        )
        return RespondResponse(
            feedback="Topic skipped. Starting a new challenge...",
            verdict="SKIPPED",
            score_delta=-0.05,
            next_action="Call /session/start to get your next challenge.",
        )

    if lower.startswith("clarify:") or lower.startswith("ask:"):
        state_snapshot = await graph.aget_state(config)
        state_values = state_snapshot.values or {}
        question_text = state_values.get("question_text", "")
        question_json = state_values.get("current_question", {})
        user_query = body.response.split(":", 1)[1].strip() if ":" in body.response else body.response.strip()
        if not user_query:
            return RespondResponse(
                feedback="Please add your clarification question after `clarify:`",
                verdict="CLARIFICATION",
                score_delta=0.0,
                next_action="Example: clarify: what consistency level is required for settlement?",
            )
        if not question_text:
            return RespondResponse(
                feedback="No active question found. Start a challenge first.",
                verdict="CLARIFICATION",
                score_delta=0.0,
                next_action="Call /session/start to begin.",
            )
        clarification = await generate_clarification(
            question_text=question_text,
            question_json=question_json,
            candidate_question=user_query,
        )
        return RespondResponse(
            feedback=clarification,
            verdict="CLARIFICATION",
            score_delta=0.0,
            next_action="Ask more follow-ups with clarify: ... or submit your final solution.",
        )

    # Normal submission — update state to 'review' and re-invoke
    await graph.aupdate_state(
        config,
        {"user_response": body.response, "interview_stage": "review"},
    )

    logger.info("[Session] Evaluating response thread_id=%s", body.thread_id)

    try:
        final_state = await graph.ainvoke(None, config=config)
    except Exception as exc:
        logger.exception("[Session] Evaluator invocation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    eval_result = final_state.get("evaluation_result", {})
    feedback = eval_result.get("feedback", "Evaluation complete.")
    verdict = eval_result.get("verdict", "NEEDS_REVISION")
    score_delta = eval_result.get("score_delta", 0.0)

    return RespondResponse(
        feedback=feedback,
        verdict=verdict,
        score_delta=score_delta,
    )


@router.get("/{thread_id}", response_model=SessionStateResponse)
async def get_session_state(thread_id: str, user_id: str, request: Request):
    """Fetch the current persisted state for a thread."""
    graph = _get_graph(request)
    config = _thread_config(thread_id, user_id)

    snapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=404, detail="Thread not found.")

    state = snapshot.values
    return SessionStateResponse(
        thread_id=thread_id,
        interview_stage=state.get("interview_stage", "idle"),
        current_topic=state.get("current_topic"),
        current_subtopic=state.get("current_subtopic"),
        knowledge_gap_score=state.get("knowledge_gap_score"),
        messages=state.get("messages", []),
    )


@router.get("/{thread_id}/history")
async def get_session_history(thread_id: str, user_id: str, request: Request):
    """Return the full feedback history for a thread."""
    graph = _get_graph(request)
    config = _thread_config(thread_id, user_id)

    snapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=404, detail="Thread not found.")

    return {
        "thread_id": thread_id,
        "feedback_history": snapshot.values.get("feedback_history", []),
        "messages": snapshot.values.get("messages", []),
    }
