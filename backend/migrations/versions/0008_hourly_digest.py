"""Unique hourly editions and the owner's revised project budget.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dates = sa.DateTime(timezone=op.get_bind().dialect.name == "postgresql")
    with op.batch_alter_table("ai_brief_control", copy_from=control_table(16)) as batch:
        batch.drop_constraint(op.f("ck_ai_brief_control_attempt_budget"), type_="check")
        batch.create_check_constraint("attempt_budget", "attempts BETWEEN 0 AND 24")
    with op.batch_alter_table("ai_brief_jobs") as batch:
        batch.add_column(sa.Column("edition_at", dates))
        batch.add_column(sa.Column("material_hash", sa.String(64)))
        batch.create_index("uq_ai_brief_jobs_edition", ["edition_at"], unique=True)


def downgrade() -> None:
    # Never discard reservations to fit the previous budget. Downgrade only when safe.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM ai_brief_control WHERE attempts > 16")):
        raise RuntimeError("Cannot downgrade while the quota ledger exceeds the previous budget")
    with op.batch_alter_table("ai_brief_jobs") as batch:
        batch.drop_index("uq_ai_brief_jobs_edition")
        batch.drop_column("material_hash")
        batch.drop_column("edition_at")
    with op.batch_alter_table("ai_brief_control", copy_from=control_table(24)) as batch:
        batch.drop_constraint(op.f("ck_ai_brief_control_attempt_budget"), type_="check")
        batch.create_check_constraint("attempt_budget", "attempts BETWEEN 0 AND 16")


def control_table(limit: int) -> sa.Table:
    # Frozen historical SQLite table for offline batch SQL. No application model imports.
    return sa.Table(
        "ai_brief_control",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("quota_day", sa.Date()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_allowed_at", sa.DateTime()),
        sa.Column("blocked_until", sa.DateTime()),
        sa.Column("blocked_code", sa.String(40)),
        sa.Column("lease_id", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime()),
        sa.CheckConstraint("id = 1", name="ck_ai_brief_control_singleton"),
        sa.CheckConstraint(
            f"attempts BETWEEN 0 AND {limit}", name="ck_ai_brief_control_attempt_budget"
        ),
        sa.CheckConstraint(
            "reserved_tokens = attempts * 4000", name="ck_ai_brief_control_token_budget"
        ),
        sa.CheckConstraint(
            "(lease_id IS NULL) = (lease_until IS NULL)", name="ck_ai_brief_control_lease_pair"
        ),
    )
