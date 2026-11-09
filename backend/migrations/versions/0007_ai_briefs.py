"""Shared AI brief reservations and seven-day results. No provider activation.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    dates = sa.DateTime(timezone=postgres)
    op.create_table(
        "ai_brief_control",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("quota_day", sa.Date()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_allowed_at", dates),
        sa.Column("blocked_until", dates),
        sa.Column("blocked_code", sa.String(40)),
        sa.Column("lease_id", sa.Uuid()),
        sa.Column("lease_until", dates),
        sa.CheckConstraint("id = 1", name="singleton"),
        sa.CheckConstraint("attempts BETWEEN 0 AND 16", name="attempt_budget"),
        sa.CheckConstraint("reserved_tokens = attempts * 4000", name="token_budget"),
        sa.CheckConstraint("(lease_id IS NULL) = (lease_until IS NULL)", name="lease_pair"),
    )
    op.execute("INSERT INTO ai_brief_control (id) VALUES (1)")
    op.create_table(
        "ai_brief_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("category_name", sa.String(120), nullable=False),
        sa.Column("quota_day", sa.Date(), nullable=False),
        sa.Column("started_at", dates, nullable=False),
        sa.Column("finished_at", dates),
        sa.Column("window_start", dates, nullable=False),
        sa.Column("window_end", dates, nullable=False),
        sa.Column("lease_until", dates, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(40)),
        sa.Column("summary", sa.Text()),
        sa.Column("articles", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'error', 'interrupted')", name="status"
        ),
        sa.CheckConstraint("window_start < window_end", name="window"),
        sa.CheckConstraint("(status = 'running') = (finished_at IS NULL)", name="finish"),
    )
    op.create_index("ix_ai_brief_jobs_category_id", "ai_brief_jobs", ["category_id"])
    op.create_index("ix_ai_brief_jobs_started_at", "ai_brief_jobs", ["started_at"])
    op.create_index("ix_ai_brief_jobs_category_day", "ai_brief_jobs", ["category_id", "quota_day"])
    op.create_index(
        "uq_ai_brief_jobs_daily_success",
        "ai_brief_jobs",
        ["category_id", "quota_day"],
        unique=True,
        sqlite_where=sa.text("status = 'success'"),
        postgresql_where=sa.text("status = 'success'"),
    )
    if postgres:
        for table in ("ai_brief_control", "ai_brief_jobs"):
            op.execute(f"REVOKE ALL ON tnr.{table} FROM PUBLIC")
            op.execute(f"""DO $$ DECLARE api_role text;
            BEGIN
                FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
                        EXECUTE format('REVOKE ALL ON tnr.{table} FROM %I', api_role);
                    END IF;
                END LOOP;
            END $$""")


def downgrade() -> None:
    op.drop_table("ai_brief_jobs")
    op.drop_table("ai_brief_control")
