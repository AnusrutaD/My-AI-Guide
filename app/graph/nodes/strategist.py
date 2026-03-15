"""
The Strategist Node.

Scans the user's knowledge graph in the vector DB, finds the biggest gap,
and sets current_topic / knowledge_gap_score for the rest of the pipeline.
"""

import json
import logging
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.graph.state import AgentState
from app.llm import get_strategist_llm
from app.models.knowledge import KnowledgeNode
from app.prompts.strategist_prompt import STRATEGIST_HUMAN_TEMPLATE, STRATEGIST_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
settings = get_settings()

_llm = get_strategist_llm()

# Bootstrap knowledge graph for a brand-new user — covers the key SDE-3 gaps
_DEFAULT_TOPICS: list[dict] = [
    {"topic": "Graphs", "subtopic": "Dijkstra / Bellman-Ford edge cases", "proficiency_score": 0.5},
    {"topic": "Trees", "subtopic": "Trie hard problems", "proficiency_score": 0.5},
    {"topic": "Dynamic Programming", "subtopic": "Interval DP / Tree DP", "proficiency_score": 0.5},
    {"topic": "Concurrency", "subtopic": "Reactive Patterns / Vert.x", "proficiency_score": 0.4},
    {"topic": "Concurrency", "subtopic": "Lock-free data structures", "proficiency_score": 0.45},
    {"topic": "System Design", "subtopic": "Rate Limiting at scale", "proficiency_score": 0.5},
    {"topic": "System Design", "subtopic": "Saga / Outbox pattern", "proficiency_score": 0.45},
    {"topic": "System Design", "subtopic": "Sharding strategies", "proficiency_score": 0.55},
    {"topic": "System Design", "subtopic": "CQRS + Event Sourcing", "proficiency_score": 0.5},
    {"topic": "Distributed Systems", "subtopic": "Consensus (Raft / Paxos)", "proficiency_score": 0.4},
    {"topic": "Distributed Systems", "subtopic": "Vector Clocks / CRDTs", "proficiency_score": 0.35},
]


async def _seed_knowledge_graph(user_id: str, db: AsyncSession) -> None:
    """Insert default nodes for a new user if none exist."""
    from uuid import uuid4

    nodes = [
        KnowledgeNode(
            id=str(uuid4()),
            user_id=user_id,
            topic=t["topic"],
            subtopic=t["subtopic"],
            proficiency_score=t["proficiency_score"],
        )
        for t in _DEFAULT_TOPICS
    ]
    db.add_all(nodes)
    await db.commit()
    logger.info("Seeded knowledge graph for user=%s with %d nodes", user_id, len(nodes))


async def _fetch_knowledge_graph(user_id: str, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(KnowledgeNode)
        .where(KnowledgeNode.user_id == user_id)
        .order_by(KnowledgeNode.proficiency_score.asc())
    )
    nodes = result.scalars().all()
    if not nodes:
        await _seed_knowledge_graph(user_id, db)
        return await _fetch_knowledge_graph(user_id, db)

    return [
        {
            "topic": n.topic,
            "subtopic": n.subtopic,
            "proficiency_score": round(n.proficiency_score, 3),
            "attempt_count": n.attempt_count,
            "last_tested": n.last_tested.isoformat() if n.last_tested else None,
        }
        for n in nodes
    ]


async def strategist_node(state: AgentState, db: AsyncSession) -> AgentState:
    """Identify the highest-priority knowledge gap for this session."""
    user_id = state["user_id"]
    logger.info("[Strategist] Running gap analysis for user=%s", user_id)

    knowledge_graph = await _fetch_knowledge_graph(user_id, db)

    recent_history = [
        f"{fb.get('topic', '?')}/{fb.get('subtopic', '?')}"
        for fb in (state.get("feedback_history") or [])[-5:]
    ]

    human_content = STRATEGIST_HUMAN_TEMPLATE.format(
        knowledge_graph_json=json.dumps(knowledge_graph, indent=2),
        recent_history="\n".join(recent_history) if recent_history else "None",
        current_date=date.today().isoformat(),
    )

    response = await _llm.ainvoke(
        [SystemMessage(content=STRATEGIST_SYSTEM_PROMPT), HumanMessage(content=human_content)]
    )

    try:
        raw = response.content.strip()
        # Strip markdown code fences if Gemini wraps in ```json
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        analysis: dict = json.loads(raw.strip())
    except (json.JSONDecodeError, IndexError) as exc:
        logger.warning("[Strategist] Failed to parse LLM JSON: %s", exc)
        # Graceful fallback: pick the lowest-scored node
        fallback = knowledge_graph[0]
        analysis = {
            "priority_topic": fallback["topic"],
            "priority_subtopic": fallback["subtopic"],
            "gap_rationale": "Lowest proficiency score in knowledge graph.",
            "knowledge_gap_score": fallback["proficiency_score"],
            "suggested_difficulty": "HARD",
            "target_companies": ["Visa", "Google"],
        }

    logger.info("[Strategist] Gap identified: %s / %s (score=%.2f)",
                analysis["priority_topic"], analysis["priority_subtopic"],
                analysis["knowledge_gap_score"])

    return {
        "current_topic": analysis["priority_topic"],
        "current_subtopic": analysis["priority_subtopic"],
        "knowledge_gap_score": analysis["knowledge_gap_score"],
        "suggested_difficulty": analysis.get("suggested_difficulty", "HARD"),
        "target_companies": analysis.get("target_companies", ["Visa", "Google"]),
        "gap_rationale": analysis.get("gap_rationale", ""),
    }
