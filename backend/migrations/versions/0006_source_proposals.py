"""Source proposals, separate from the shared catalog.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    dates = sa.DateTime(timezone=postgres)
    op.create_table(
        "source_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_key", sa.String(64), nullable=False),
        sa.Column("url", sa.String(2048)),
        sa.Column("note", sa.String(500)),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("follow_on_approval", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", dates, nullable=False),
        sa.Column("decided_at", dates),
        sa.Column("decided_by", sa.Uuid(), sa.ForeignKey("app_users.id", ondelete="SET NULL")),
        sa.Column("reason", sa.String(500)),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="SET NULL")),
        sa.Column("approved_name", sa.String(200)),
        sa.Column("approved_feed_url", sa.String(2048)),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')", name="valid_status"
        ),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 200", name="proposal_name"),
        sa.CheckConstraint("url IS NULL OR length(url) BETWEEN 1 AND 2048", name="proposal_url"),
        sa.CheckConstraint("note IS NULL OR length(note) <= 500", name="proposal_note"),
        sa.CheckConstraint(
            "reason IS NULL OR length(reason) BETWEEN 1 AND 500", name="proposal_reason"
        ),
        sa.CheckConstraint("(status = 'pending') = (decided_at IS NULL)", name="proposal_decision"),
        sa.CheckConstraint("status <> 'rejected' OR reason IS NOT NULL", name="rejection_reason"),
    )
    for column in ("user_id", "category_id", "decided_by", "source_id"):
        op.create_index(f"ix_source_proposals_{column}", "source_proposals", [column])
    op.create_index(
        "ix_source_proposals_status_created", "source_proposals", ["status", "created_at", "id"]
    )
    op.create_index(
        "uq_source_proposals_pending_name",
        "source_proposals",
        ["user_id", "name_key"],
        unique=True,
        sqlite_where=sa.text("status = 'pending'"),
        postgresql_where=sa.text("status = 'pending'"),
    )
    if postgres:
        op.execute("REVOKE ALL ON tnr.source_proposals FROM PUBLIC")
        op.execute("REVOKE ALL ON tnr.source_proposals_id_seq FROM PUBLIC")
        op.execute("""DO $$ DECLARE api_role text;
        BEGIN
            FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
                    EXECUTE format('REVOKE ALL ON tnr.source_proposals FROM %I', api_role);
                    EXECUTE format('REVOKE ALL ON tnr.source_proposals_id_seq FROM %I', api_role);
                END IF;
            END LOOP;
        END $$""")


def downgrade() -> None:
    op.drop_table("source_proposals")
