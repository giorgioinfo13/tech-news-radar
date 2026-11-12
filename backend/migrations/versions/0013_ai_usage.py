"""Keep content-free AI usage beyond edition retention."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

TOKEN_FIELDS = ("counted_tokens", "input_tokens", "output_tokens", "thought_tokens", "total_tokens")


def upgrade() -> None:
    op.create_table(
        "ai_brief_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edition_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(40)),
        *(sa.Column(name, sa.Integer()) for name in TOKEN_FIELDS),
        sa.Column("usage_validated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("estimated_nano_usd", sa.BigInteger()),
        sa.Column("reserved_nano_usd", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'error', 'interrupted')", name="status"
        ),
        sa.CheckConstraint("reserved_nano_usd >= 0", name="reservation"),
        sa.CheckConstraint("estimated_nano_usd >= 0", name="estimate"),
        *(sa.CheckConstraint(f"{name} BETWEEN 0 AND 10000000", name=name) for name in TOKEN_FIELDS),
    )
    op.create_index("ix_ai_brief_usage_started_at", "ai_brief_usage", ["started_at"])
    # Copy only retained attempts and safe numeric diagnostics. Never fabricate usage
    # for old successes or copy prompts, summaries, articles, or raw provider data.
    columns = (
        "id, started_at, edition_at, finished_at, dispatched_at, lease_until, model, "
        "status, error_code, reserved_nano_usd"
    )
    metrics = ", ".join(
        f"CASE WHEN json_typeof(diagnostics->'{name}') = 'number' "
        f"AND diagnostics->>'{name}' ~ '^[0-9]{{1,8}}$' "
        f"THEN CASE WHEN (diagnostics->>'{name}')::integer <= 10000000 "
        f"THEN (diagnostics->>'{name}')::integer END END"
        for name in TOKEN_FIELDS
    )
    op.execute(
        f"INSERT INTO ai_brief_usage ({columns}, {', '.join(TOKEN_FIELDS)}) "
        f"SELECT {columns}, {metrics} FROM ai_brief_jobs"
    )
    op.execute("REVOKE ALL ON tnr.ai_brief_usage FROM PUBLIC")
    op.execute("""DO $$ DECLARE api_role text;
    BEGIN
        FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
                EXECUTE format('REVOKE ALL ON tnr.ai_brief_usage FROM %I', api_role);
            END IF;
        END LOOP;
    END $$""")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM ai_brief_usage")):
        raise RuntimeError("Cannot discard AI usage history")
    op.drop_index("ix_ai_brief_usage_started_at", table_name="ai_brief_usage")
    op.drop_table("ai_brief_usage")
