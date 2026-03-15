"""
LangGraph StateGraph — the orchestration backbone.

Flow:
  START
    └─► strategist   (Gemini: gap analysis)
          └─► scraper       (Tavily: trend search)
                └─► question_setter  (Claude: craft question)
                      └─► [INTERRUPT — wait for user response]
                            └─► evaluator   (Claude: grade response)
                                  └─► END

On the next user message the checkpointer rehydrates state and routes:
  - stage == "idle"    → restart from strategist
  - stage == "review"  → resume at evaluator
"""

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.graph import CompiledGraph

from app.config import get_settings
from app.graph.state import AgentState
from app.graph.nodes import (
    evaluator_node,
    question_setter_node,
    scraper_node,
    strategist_node,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Node wrappers ─────────────────────────────────────────────────────────────
# LangGraph passes state dict only; DB sessions are injected via dependency
# injection at the API layer and stored in the state context.  Here we make
# thin wrappers that extract the db handle injected via RunnableConfig extras.


def _make_strategist(db_factory):
    async def _node(state: AgentState) -> AgentState:
        async with db_factory() as db:
            return await strategist_node(state, db)
    _node.__name__ = "strategist"
    return _node


def _make_evaluator(db_factory):
    async def _node(state: AgentState) -> AgentState:
        async with db_factory() as db:
            return await evaluator_node(state, db)
    _node.__name__ = "evaluator"
    return _node


def _route_after_question(state: AgentState) -> str:
    """
    After question_setter sets stage='testing' we interrupt and wait for the
    user to submit their code.  The graph resumes by calling it again with
    stage='review', which routes to the evaluator.
    """
    stage = state.get("interview_stage", "idle")
    if stage == "review":
        return "evaluator"
    # stage == "testing" → interrupt (graph halts here until next invocation)
    return END


def build_graph(db_factory) -> CompiledGraph:
    """
    Compile the LangGraph StateGraph with the given async DB session factory.

    Args:
        db_factory: An async context-manager factory — ``async with db_factory() as db``.
                    Typically ``AsyncSessionLocal`` from ``app.database``.
    """
    from app.database import AsyncSessionLocal  # avoid circular at module load

    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("strategist", _make_strategist(db_factory))
    graph.add_node("scraper", scraper_node)
    graph.add_node("question_setter", question_setter_node)
    graph.add_node("evaluator", _make_evaluator(db_factory))

    # Edges
    graph.add_edge(START, "strategist")
    graph.add_edge("strategist", "scraper")
    graph.add_edge("scraper", "question_setter")

    # After question_setter: branch on interview_stage
    graph.add_conditional_edges(
        "question_setter",
        _route_after_question,
        {
            "evaluator": "evaluator",
            END: END,
        },
    )
    graph.add_edge("evaluator", END)

    return graph.compile()


async def get_checkpointer() -> tuple[Any, Any | None]:
    """
    Return an appropriate checkpointer based on CHECKPOINTER_BACKEND env var.

    - "postgres"  → AsyncPostgresSaver (production)
    - "sqlite"    → AsyncSqliteSaver   (local dev / CI)
    """
    backend = settings.checkpointer_backend.lower()

    async def _enter(maybe_ctx: Any) -> tuple[Any, Any | None]:
        # Some langgraph saver constructors return async context managers.
        if hasattr(maybe_ctx, "__aenter__"):
            saver = await maybe_ctx.__aenter__()
            return saver, maybe_ctx
        return maybe_ctx, None

    if backend == "postgres":
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            # psycopg3 connection string — strip the SQLAlchemy driver prefix
            conn_str = settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")
            checkpointer, ctx = await _enter(AsyncPostgresSaver.from_conn_string(conn_str))
            await checkpointer.setup()
            logger.info("[Checkpointer] Using AsyncPostgresSaver")
            return checkpointer, ctx
        except Exception as exc:
            logger.warning("[Checkpointer] Postgres unavailable (%s) — falling back to SQLite", exc)

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        checkpointer, ctx = await _enter(AsyncSqliteSaver.from_conn_string("/tmp/ai_guide_checkpoints.db"))
        await checkpointer.setup()
        logger.info("[Checkpointer] Using AsyncSqliteSaver at /tmp/ai_guide_checkpoints.db")
        return checkpointer, ctx
    except Exception as exc:
        logger.warning("[Checkpointer] SQLite unavailable (%s) — falling back to in-memory saver", exc)
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver(), None
