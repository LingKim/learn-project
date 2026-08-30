"""add user profiles and avatar upload purpose

Revision ID: 20260830_01
Revises: ac3e06160525
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260830_01"
down_revision: str | Sequence[str] | None = "ac3e06160525"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "file_upload_sessions",
        sa.Column(
            "purpose",
            sa.String(length=32),
            server_default="knowledge_document",
            nullable=False,
        ),
    )
    op.add_column(
        "file_upload_sessions", sa.Column("result_file_asset_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "file_upload_sessions", sa.Column("requested_profile_version", sa.Integer(), nullable=True)
    )
    op.alter_column("file_upload_sessions", "knowledge_base_id", nullable=True)
    op.create_check_constraint(
        "ck_file_upload_purpose",
        "file_upload_sessions",
        "purpose IN ('knowledge_document', 'avatar')",
    )
    op.create_foreign_key(
        "fk_file_upload_sessions_result_file_asset_id",
        "file_upload_sessions",
        "file_assets",
        ["result_file_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE file_policy_versions
        SET rules = jsonb_set(
            rules,
            '{avatar}',
            jsonb_build_object(
                'extensions', jsonb_build_array('jpg', 'jpeg', 'png', 'webp'),
                'max_bytes', 5242880,
                'max_dimension', 8192,
                'max_pixels', 40000000
            ),
            true
        )
        """
    )
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("target_job", sa.String(length=120), nullable=True),
        sa.Column("experience_months", sa.Integer(), nullable=True),
        sa.Column("target_level", sa.String(length=16), nullable=True),
        sa.Column("target_skills", postgresql.ARRAY(sa.String(length=50)), nullable=True),
        sa.Column("focus_topics", postgresql.ARRAY(sa.String(length=80)), nullable=True),
        sa.Column("learning_goal", sa.Text(), nullable=True),
        sa.Column("preferred_language", sa.String(length=8), nullable=True),
        sa.Column("avatar_file_asset_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "experience_months IS NULL OR experience_months BETWEEN 0 AND 720",
            name="ck_user_profiles_experience_months",
        ),
        sa.CheckConstraint(
            "target_level IS NULL OR target_level IN "
            "('intern', 'junior', 'intermediate', 'senior', 'expert')",
            name="ck_user_profiles_target_level",
        ),
        sa.CheckConstraint(
            "preferred_language IS NULL OR preferred_language IN ('zh-CN', 'en-US')",
            name="ck_user_profiles_preferred_language",
        ),
        sa.CheckConstraint("version >= 1", name="ck_user_profiles_version"),
        sa.ForeignKeyConstraint(["avatar_file_asset_id"], ["file_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
    )
    op.create_index("ix_user_profiles_avatar", "user_profiles", ["avatar_file_asset_id"])


def downgrade() -> None:
    op.drop_index("ix_user_profiles_avatar", table_name="user_profiles")
    op.drop_table("user_profiles")
    # 旧 schema 要求每个上传会话必须绑定知识库，无法表达 avatar 会话。
    # 降级属于显式回滚，先清除仅由本版本创建的头像记录，避免恢复 NOT NULL 失败。
    op.execute("DELETE FROM file_assets WHERE purpose = 'avatar'")
    op.execute("DELETE FROM file_upload_sessions WHERE purpose = 'avatar'")
    op.execute("DELETE FROM stored_objects WHERE storage_domain = 'avatars'")
    op.execute("UPDATE file_policy_versions SET rules = rules - 'avatar'")
    op.drop_constraint(
        "fk_file_upload_sessions_result_file_asset_id",
        "file_upload_sessions",
        type_="foreignkey",
    )
    op.drop_constraint("ck_file_upload_purpose", "file_upload_sessions", type_="check")
    op.alter_column("file_upload_sessions", "knowledge_base_id", nullable=False)
    op.drop_column("file_upload_sessions", "requested_profile_version")
    op.drop_column("file_upload_sessions", "result_file_asset_id")
    op.drop_column("file_upload_sessions", "purpose")
