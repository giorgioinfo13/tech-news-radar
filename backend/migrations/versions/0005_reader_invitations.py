"""Explicit email invitations and reader-only runtime provisioning.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    dates = sa.DateTime(timezone=postgres)
    op.create_table(
        "reader_invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "email", sa.String(254, collation="C") if postgres else sa.String(254), nullable=False
        ),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("invited_by", sa.Uuid(), sa.ForeignKey("app_users.id"), nullable=False),
        sa.Column("created_at", dates, nullable=False),
        sa.Column("accepted_at", dates),
        sa.Column("accepted_subject", sa.Uuid()),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("accepted_subject"),
        sa.CheckConstraint(
            "length(email) BETWEEN 3 AND 254 AND email = lower(trim(email))",
            name="normalized_email",
        ),
        sa.CheckConstraint("length(trim(display_name)) BETWEEN 1 AND 120", name="invitation_name"),
        sa.CheckConstraint(
            "(accepted_at IS NULL) = (accepted_subject IS NULL)", name="invitation_claim"
        ),
    )
    op.create_index("ix_reader_invitations_invited_by", "reader_invitations", ["invited_by"])
    if postgres:
        op.execute("REVOKE ALL ON tnr.reader_invitations FROM PUBLIC")
        op.execute("""
            DO $$ DECLARE api_role text;
            BEGIN
                FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
                        EXECUTE format('REVOKE ALL ON tnr.reader_invitations FROM %I', api_role);
                    END IF;
                END LOOP;
            END $$
        """)
        # SQL connections do not carry end-user identity. These policies constrain
        # runtime inserts, not per-user reads. Owner/operator access is unchanged.
        op.execute("ALTER TABLE tnr.app_users ENABLE ROW LEVEL SECURITY")
        op.execute("CREATE POLICY app_users_read ON tnr.app_users FOR SELECT USING (true)")
        op.execute("""
            CREATE POLICY app_users_insert_reader ON tnr.app_users FOR INSERT WITH CHECK (
                role = 'reader' AND active AND supabase_subject IS NOT NULL
                AND id <> '00000000-0000-0000-0000-000000000001'::uuid
                AND EXISTS (SELECT 1 FROM tnr.reader_invitations i
                    WHERE i.accepted_subject = app_users.supabase_subject
                    AND i.accepted_at IS NOT NULL)
            )
        """)
        # Grants remain an explicit, separately authorized operator operation.


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # Remove runtime provisioning before removing its database constraints.
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='tnr_app') THEN
                REVOKE INSERT ON tnr.app_users FROM tnr_app;
            END IF;
        END $$""")
        op.execute("DROP POLICY app_users_insert_reader ON tnr.app_users")
        op.execute("DROP POLICY app_users_read ON tnr.app_users")
        op.execute("ALTER TABLE tnr.app_users DISABLE ROW LEVEL SECURITY")
    op.drop_table("reader_invitations")
