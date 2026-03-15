import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm import get_question_setter_llm

_llm = get_question_setter_llm()

CLARIFIER_SYSTEM_PROMPT = """\
You are a technical interviewer answering candidate clarifying questions.

Rules:
1) Clarify requirements and constraints only.
2) Do NOT provide full solutions, architectures, or code.
3) If the question asks for assumptions not specified, state a reasonable assumption explicitly.
4) Keep the response concise and actionable (3-8 bullet points max).
5) Preserve interview rigor for SDE-3 level.
"""


async def generate_clarification(
    *,
    question_text: str,
    question_json: dict | None,
    candidate_question: str,
) -> str:
    question_struct = json.dumps(question_json or {}, indent=2)
    prompt = f"""\
Original interview question:
{question_text}

Structured question metadata (if available):
{question_struct}

Candidate clarifying question:
{candidate_question}

Return only the clarification response.
"""
    resp = await _llm.ainvoke(
        [SystemMessage(content=CLARIFIER_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    return (resp.content or "").strip()
