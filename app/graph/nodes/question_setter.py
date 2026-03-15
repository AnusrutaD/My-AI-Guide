"""
The Question Setter Node.

Synthesises the Strategist's gap analysis and Scraper's trend context into a
single, production-grade interview question.
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.state import AgentState
from app.llm import get_question_setter_llm
from app.prompts.strategist_prompt import QUESTION_SETTER_HUMAN_TEMPLATE, QUESTION_SETTER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
settings = get_settings()

_llm = get_question_setter_llm()


def _render_question(question_json: dict) -> str:
    """Turn the structured question JSON into a human-readable prompt string."""
    q = question_json
    lines = [
        f"## [{q.get('question_type', 'CODING')}] {q.get('title', 'Challenge')}",
        f"**Estimated time:** {q.get('expected_time_minutes', 30)} min",
        "",
        q.get("prompt", ""),
        "",
        "---",
        "*Reply with your solution. Type `hint` to get a hint. Type `skip` to move to the next topic.*",
    ]
    return "\n".join(lines)


async def question_setter_node(state: AgentState) -> AgentState:
    """Generate a custom challenge from gap analysis + trend context."""
    topic = state.get("current_topic", "System Design")
    subtopic = state.get("current_subtopic", "general")
    companies = state.get("target_companies", ["Visa", "Google"])
    difficulty = state.get("suggested_difficulty", "HARD")
    gap_rationale = state.get("gap_rationale", "")
    trend_context = state.get("recent_trend_context", "No trend data available.")

    # Pass the last 2 evaluation results as context so Claude avoids repetition
    recent_feedback = []
    for fb in (state.get("feedback_history") or [])[-2:]:
        recent_feedback.append(
            f"Topic: {fb.get('topic', '?')} | Verdict: {fb.get('verdict', '?')}\n"
            f"Key issues: {', '.join(fb.get('critical_bugs', []))}"
        )

    logger.info("[QuestionSetter] Crafting %s question for %s / %s", difficulty, topic, subtopic)

    human_content = QUESTION_SETTER_HUMAN_TEMPLATE.format(
        topic=topic,
        subtopic=subtopic,
        target_companies=", ".join(companies),
        difficulty=difficulty,
        gap_rationale=gap_rationale,
        trend_context=trend_context[:1500],  # keep context window sane
        recent_feedback="\n\n".join(recent_feedback) if recent_feedback else "None yet.",
    )

    response = await _llm.ainvoke(
        [SystemMessage(content=QUESTION_SETTER_SYSTEM_PROMPT), HumanMessage(content=human_content)]
    )

    try:
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        question_json: dict = json.loads(raw.strip())
    except (json.JSONDecodeError, IndexError) as exc:
        logger.warning("[QuestionSetter] JSON parse failed: %s — using raw text as prompt", exc)
        question_json = {
            "question_type": "CODING",
            "title": f"{topic}: {subtopic}",
            "prompt": response.content,
            "hints": [],
            "expected_time_minutes": 30,
            "evaluation_focus": ["correctness", "complexity", "edge cases"],
        }

    question_text = _render_question(question_json)
    logger.info("[QuestionSetter] Question ready: %s", question_json.get("title"))

    return {
        "current_question": question_json,
        "question_text": question_text,
        "interview_stage": "testing",          # ← graph interrupts here; waiting for user
        "messages": [{"role": "assistant", "content": question_text}],
    }
