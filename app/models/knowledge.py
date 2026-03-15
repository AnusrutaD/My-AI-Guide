from datetime import datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KnowledgeNode(Base):
    """
    Stores per-user topic proficiency in the knowledge graph.

    Each row represents a (user, topic, subtopic) triplet.
    The `embedding` column holds a 1536-dim vector (OpenAI text-embedding-3-small)
    so the Strategist can do semantic nearest-neighbour gap search without
    requiring exact topic-name matches.
    """

    __tablename__ = "knowledge_nodes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    subtopic: Mapped[str] = mapped_column(String(128), nullable=False, default="general")

    # 0.0 → never attempted / unknown  |  1.0 → mastered
    proficiency_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_tested: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Semantic embedding for gap-search queries
    embedding: Mapped[list | None] = mapped_column(Vector(1536), nullable=True)

    # Freeform metadata: error patterns, preferred language, etc.
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_knowledge_nodes_user_topic", "user_id", "topic", "subtopic", unique=True),
        # IVFFlat index for ANN search — tune lists= after data grows
        Index(
            "ix_knowledge_nodes_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        return f"<KnowledgeNode user={self.user_id} {self.topic}/{self.subtopic} score={self.proficiency_score:.2f}>"


class SessionLog(Base):
    """Immutable audit log of every Q&A exchange."""

    __tablename__ = "session_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    user_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
