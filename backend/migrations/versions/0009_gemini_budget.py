"""Exact monthly app budget and one-time dispatch marker. Does not activate AI.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    op.create_table(
        "ai_brief_budget",
        sa.Column("month", sa.Date(), primary_key=True),
        sa.Column("reserved_nano_usd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("reserved_nano_usd BETWEEN 0 AND 2000000000", name="monthly_budget"),
    )
    op.add_column("ai_brief_jobs", sa.Column("budget_month", sa.Date()))
    op.add_column(
        "ai_brief_jobs",
        sa.Column("reserved_nano_usd", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column("ai_brief_jobs", sa.Column("dispatched_at", sa.DateTime(timezone=postgres)))
    op.add_column("ai_brief_jobs", sa.Column("diagnostics", sa.JSON()))
    if postgres:
        op.execute("REVOKE ALL ON tnr.ai_brief_budget FROM PUBLIC")
        op.execute("""DO $$ DECLARE api_role text;
        BEGIN
            FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
                    EXECUTE format('REVOKE ALL ON tnr.ai_brief_budget FROM %I', api_role);
                END IF;
            END LOOP;
        END $$""")


def downgrade() -> None:
    # A downgrade must never erase a paid reservation, including old months.
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM ai_brief_budget WHERE reserved_nano_usd > 0")
    ):
        raise RuntimeError("Cannot discard monetary reservations")
    for name in ("diagnostics", "dispatched_at", "reserved_nano_usd", "budget_month"):
        op.drop_column("ai_brief_jobs", name)
    op.drop_table("ai_brief_budget")
