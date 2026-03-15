"""
The Evaluator Node, channelling a
Senior Staff Engineer at Visa's Core Payments Infrastructure.

This node does NOT forgive sloppiness.
"""

import logging
import re
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.graph.state import AgentState
from app.llm import get_evaluator_llm
from app.models.knowledge import KnowledgeNode, SessionLog
from app.prompts.evaluator_prompt import EVALUATOR_HUMAN_TEMPLATE, EVALUATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
settings = get_settings()

_llm = get_evaluator_llm()

_VERDICT_SCORE_MAP = {
    "PASS_SENIOR": 0.15,
    "NEEDS_REVISION": 0.0,
    "BACK_TO_DRAWING_BOARD": -0.15,
}


def _parse_score_delta(text: str, verdict: str) -> float:
    """Extract SCORE DELTA float from evaluator output or fall back to verdict map."""
    match = re.search(r"SCORE DELTA[:\s]+([+-]?\d*\.?\d+)", text, re.IGNORECASE)
    if match:
        try:
            return max(-0.3, min(0.3, float(match.group(1))))
        except ValueError:
            pass
    return _VERDICT_SCORE_MAP.get(verdict, 0.0)


async def _update_knowledge_score(
    user_id: str,
    topic: str,
    subtopic: str,
    delta: float,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.user_id == user_id,
            KnowledgeNode.topic == topic,
            KnowledgeNode.subtopic == subtopic,
        )
    )
    node = result.scalar_one_or_none()
    if node:
        node.proficiency_score = max(0.0, min(1.0, node.proficiency_score + delta))
        node.attempt_count += 1
        node.last_tested = datetime.utcnow()
        await db.commit()
        logger.info(
            "[Evaluator] Updated %s/%s score → %.3f (Δ%+.3f)",
            topic, subtopic, node.proficiency_score, delta,
        )


async def _log_session(
    user_id: str,
    thread_id: str,
    topic: str,
    question_text: str,
    user_response: str,
    evaluation: dict,
    score_delta: float,
    db: AsyncSession,
) -> None:
    log = SessionLog(
        user_id=user_id,
        thread_id=thread_id,
        topic=topic,
        question=question_text,
        user_response=user_response,
        evaluation=evaluation,
        score_delta=score_delta,
    )
    db.add(log)
    await db.commit()


async def evaluator_node(state: AgentState, db: AsyncSession) -> AgentState:
    """Evaluate the user's response with Staff Engineer rigour."""
    user_id = state["user_id"]
    topic = state.get("current_topic", "Unknown")
    subtopic = state.get("current_subtopic", "general")
    question = state.get("current_question", {})
    question_text = state.get("question_text", question.get("prompt", ""))
    user_response = state.get("user_response", "")
    trend_context = state.get("recent_trend_context", "")
    thread_id = state.get("thread_id", "default")

    if not user_response.strip():
        logger.warning("[Evaluator] Empty user response for user=%s", user_id)
        return {
            "evaluation_result": {"error": "No response submitted."},
            "interview_stage": "idle",
        }

    logger.info("[Evaluator] Evaluating response from user=%s on %s/%s", user_id, topic, subtopic)

    human_content = EVALUATOR_HUMAN_TEMPLATE.format(
        topic=topic,
        subtopic=subtopic,
        question=question_text,
        user_response=user_response,
        trend_context=trend_context[:800],
    )

    response = await _llm.ainvoke(
        [SystemMessage(content=EVALUATOR_SYSTEM_PROMPT), HumanMessage(content=human_content)]
    )

    raw_feedback = response.content

    # Extract verdict
    verdict_match = re.search(
        r"\*\*VERDICT[:\s]+\*\*(PASS_SENIOR|NEEDS_REVISION|BACK_TO_DRAWING_BOARD)",
        raw_feedback,
        re.IGNORECASE,
    )
    verdict = verdict_match.group(1).upper() if verdict_match else "NEEDS_REVISION"
    score_delta = _parse_score_delta(raw_feedback, verdict)

    evaluation_result = {
        "verdict": verdict,
        "score_delta": score_delta,
        "feedback": raw_feedback,
        "topic": topic,
        "subtopic": subtopic,
    }

    # Persist to DB
    await _update_knowledge_score(user_id, topic, subtopic, score_delta, db)
    await _log_session(
        user_id, thread_id, topic, question_text, user_response, evaluation_result, score_delta, db
    )

    # Append a compact summary to the feedback history (for Strategist context)
    critical_bugs: list[str] = []
    bugs_block = re.search(
        r"\*\*CRITICAL BUGS.*?:\*\*(.*?)\*\*COMPLEXITY", raw_feedback, re.DOTALL | re.IGNORECASE
    )
    if bugs_block:
        critical_bugs = [
            line.strip("- ").strip()
            for line in bugs_block.group(1).strip().split("\n")
            if line.strip() and line.strip() != "None"
        ][:3]

    history_entry = {
        "topic": topic,
        "subtopic": subtopic,
        "verdict": verdict,
        "score_delta": score_delta,
        "critical_bugs": critical_bugs,
    }

    logger.info("[Evaluator] Verdict=%s, Δ=%.3f for user=%s", verdict, score_delta, user_id)

    return {
        "evaluation_result": evaluation_result,
        "score_delta": score_delta,
        "interview_stage": "idle",        # reset to trigger next Strategist cycle
        "feedback_history": [history_entry],
        "messages": [{"role": "assistant", "content": raw_feedback}],
    }
