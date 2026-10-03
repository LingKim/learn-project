"""Bodyless AgentRun snapshots bound to the real practice queue."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261003_05"
down_revision = "20261003_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "owner_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "practice_run_id",
            sa.UUID(),
            sa.ForeignKey("practice_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_key", sa.String(64), nullable=False),
        sa.Column("scene_key", sa.String(64), nullable=False),
        sa.Column("root_prompt_version_id", sa.UUID(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("input_reference", postgresql.JSONB(), nullable=False),
        sa.Column("output_reference", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("trace_ids", postgresql.JSONB(), nullable=False),
        sa.Column("error_key", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("practice_run_id", name="uq_agent_run_practice"),
        sa.CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_agent_run_status",
        ),
    )
    op.create_index("ix_agent_run_owner", "agent_runs", ["owner_user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("agent_runs")
