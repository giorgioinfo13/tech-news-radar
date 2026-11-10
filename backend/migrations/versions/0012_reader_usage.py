"""Store the most recent authorized app validation, without an event history."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    op.add_column("app_users", sa.Column("last_seen_at", sa.DateTime(timezone=postgres)))
    if postgres:
        # SQL connections carry the backend identity, not the reader JWT.
        # Column-level grants separately constrain this policy to telemetry writes.
        op.execute("""CREATE POLICY app_users_update_usage ON tnr.app_users
            FOR UPDATE USING (active) WITH CHECK (active)""")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY app_users_update_usage ON tnr.app_users")
    op.drop_column("app_users", "last_seen_at")
