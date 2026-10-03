"""Account navigation position preference.

Revision ID: 20261003_01
Revises: 20261002_02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_01"
down_revision: str | Sequence[str] | None = "20261002_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("navigation_position", sa.String(8), nullable=False, server_default="left"),
    )
    op.create_check_constraint(
        "ck_user_profiles_navigation_position",
        "user_profiles",
        "navigation_position IN ('left', 'top')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_profiles_navigation_position", "user_profiles", type_="check")
    op.drop_column("user_profiles", "navigation_position")
