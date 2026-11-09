"""Persist RSS attempt limits before network I/O.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column(
            "last_attempt_at", sa.DateTime(timezone=op.get_bind().dialect.name == "postgresql")
        ),
    )
    # Include interrupted runs from the old collector, without changing article retention.
    op.execute("""UPDATE sources SET last_attempt_at = (
        SELECT max(started_at) FROM collection_runs WHERE collection_runs.source_id = sources.id
    )""")


def downgrade() -> None:
    op.drop_column("sources", "last_attempt_at")
