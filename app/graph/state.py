from operator import add
from typing import Annotated, Any

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    # ── Identity ─────────────────────────────────────────────────────────────
    user_id: str
    thread_id: str

    # ── Session lifecycle ─────────────────────────────────────────────────────
    # "idle"    → Strategist + Scraper + QuestionSetter run
    # "testing" → waiting for user's code/answer (graph is interrupted here)
    # "review"  → Evaluator runs after user submits response
    interview_stage: str

    # ── Strategist output ─────────────────────────────────────────────────────
    current_topic: str
    current_subtopic: str
    knowledge_gap_score: float       # 0.0 = critical gap, 1.0 = mastered
    suggested_difficulty: str        # MEDIUM | HARD | EXPERT
    target_companies: list[str]
    gap_rationale: str

    # ── Scraper output ────────────────────────────────────────────────────────
    recent_trend_context: str        # raw text block from Tavily

    # ── Question Setter output ────────────────────────────────────────────────
    current_question: dict[str, Any] # full question JSON from QuestionSetter
    question_text: str               # rendered prompt sent to user

    # ── Evaluator input ───────────────────────────────────────────────────────
    user_response: str               # code / design answer submitted by user

    # ── Evaluator output ──────────────────────────────────────────────────────
    evaluation_result: dict[str, Any]
    score_delta: float

    # ── Running history (append-only via Annotated[..., add]) ─────────────────
    # LangGraph merges these lists across checkpoints automatically
    feedback_history: Annotated[list[dict], add]
    messages: Annotated[list[Any], add]


# ── Sentinel defaults ─────────────────────────────────────────────────────────
DEFAULT_STATE: AgentState = {
    "interview_stage": "idle",
    "knowledge_gap_score": 0.5,
    "feedback_history": [],
    "messages": [],
    "target_companies": ["Visa", "Google", "Meta"],
}
