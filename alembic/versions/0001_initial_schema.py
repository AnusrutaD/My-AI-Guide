"""Initial schema — knowledge_nodes + session_logs with pgvector

Revision ID: 0001
Revises:
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension exists (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── knowledge_nodes ──────────────────────────────────────────────────────
    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("subtopic", sa.String(128), nullable=False, server_default="general"),
        sa.Column("proficiency_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_tested", sa.DateTime(timezone=True), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_knowledge_nodes_user_id", "knowledge_nodes", ["user_id"])
    op.create_index(
        "ix_knowledge_nodes_user_topic",
        "knowledge_nodes",
        ["user_id", "topic", "subtopic"],
        unique=True,
    )
    # IVFFlat index for ANN — requires at least ~100 rows before it's effective.
    # Created with lists=10 for small initial dataset; tune up when you have >10k rows.
    op.execute(
        """
        CREATE INDEX ix_knowledge_nodes_embedding
        ON knowledge_nodes
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 10)
        """
    )

    # ── session_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "session_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("thread_id", sa.String(128), nullable=False),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("user_response", sa.Text(), nullable=True),
        sa.Column("evaluation", sa.JSON(), nullable=True),
        sa.Column("score_delta", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_session_logs_user_id", "session_logs", ["user_id"])
    op.create_index("ix_session_logs_thread_id", "session_logs", ["thread_id"])


def downgrade() -> None:
    op.drop_table("session_logs")
    op.drop_index("ix_knowledge_nodes_embedding", table_name="knowledge_nodes")
    op.drop_table("knowledge_nodes")
