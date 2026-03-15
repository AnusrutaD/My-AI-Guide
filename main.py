"""
SDE-3 Personal Mentor Agent — FastAPI entry point.

Startup sequence:
  1. Init PostgreSQL tables (including pgvector extension)
  2. Initialise LangGraph checkpointer (Postgres or SQLite fallback)
  3. Compile the StateGraph with the DB session factory
  4. Mount routers
"""

import logging
import sys
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import AsyncSessionLocal, init_db
from app.graph.workflow import build_graph, get_checkpointer
from app.routers import session as session_router
from app.routers import status as status_router
from app.routers import webhook as webhook_router

settings = get_settings()

# ── Structured logging setup ──────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
)
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== SDE-3 Mentor Agent: starting up ===")

    # 1. Database
    try:
        await init_db()
        logger.info("[DB] Tables initialised (pgvector extension enabled)")
    except Exception as exc:
        logger.warning("[DB] Could not initialise DB: %s — continuing (local dev mode?)", exc)

    # 2. Checkpointer
    checkpointer, checkpointer_ctx = await get_checkpointer()
    app.state.checkpointer = checkpointer
    app.state.checkpointer_ctx = checkpointer_ctx

    # 3. Compile graph
    # Re-compile with checkpointer now that it's ready
    from langgraph.graph import END, START, StateGraph
    from app.graph.state import AgentState
    from app.graph.nodes import (
        evaluator_node,
        question_setter_node,
        scraper_node,
        strategist_node,
    )
    from app.graph.workflow import _make_strategist, _make_evaluator, _route_after_question

    graph = StateGraph(AgentState)
    graph.add_node("strategist", _make_strategist(AsyncSessionLocal))
    graph.add_node("scraper", scraper_node)
    graph.add_node("question_setter", question_setter_node)
    graph.add_node("evaluator", _make_evaluator(AsyncSessionLocal))
    graph.add_edge(START, "strategist")
    graph.add_edge("strategist", "scraper")
    graph.add_edge("scraper", "question_setter")
    graph.add_conditional_edges(
        "question_setter",
        _route_after_question,
        {"evaluator": "evaluator", END: END},
    )
    graph.add_edge("evaluator", END)
    app.state.graph = graph.compile(checkpointer=checkpointer)

    logger.info("[Graph] StateGraph compiled with checkpointer=%s", type(checkpointer).__name__)
    logger.info("=== Startup complete — listening on %s:%s ===", settings.app_host, settings.app_port)

    yield

    # Teardown
    logger.info("=== Shutting down ===")
    from app.database import engine
    await engine.dispose()
    ctx = getattr(app.state, "checkpointer_ctx", None)
    if ctx is not None and hasattr(ctx, "__aexit__"):
        await ctx.__aexit__(None, None, None)


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="SDE-3 Personal Mentor Agent",
        description=(
            "A multi-agent system that bridges your DSA & System Design gaps "
            "using LangGraph, Claude 3.5 Sonnet, and Gemini 1.5 Pro."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(session_router.router)
    app.include_router(status_router.router)
    app.include_router(webhook_router.router)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "checkpointer": type(app.state.checkpointer).__name__,
        }

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
        log_level="info",
    )
