"""Shared catalog with personal subscriptions and read states.

Revision ID: 0003
Revises: 0002
"""

from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OWNER = UUID("00000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    dates = sa.DateTime(timezone=op.get_bind().dialect.name == "postgresql")
    users = op.create_table(
        "app_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(20), server_default="reader", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", dates, server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'reader')", name=op.f("ck_app_users_valid_role")),
        sa.CheckConstraint(
            "length(trim(display_name)) > 0", name=op.f("ck_app_users_display_name_not_blank")
        ),
    )
    # A reserved local owner, never the first registrant or a browser-supplied identity.
    op.bulk_insert(
        users, [{"id": OWNER, "display_name": "Local owner", "role": "admin", "active": True}]
    )
    subscriptions = op.create_table(
        "subscriptions",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("created_at", dates, server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_subscriptions_source_id", "subscriptions", ["source_id"])
    reads = op.create_table(
        "article_read_states",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "article_id",
            sa.Integer(),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("read_at", dates, server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_article_read_states_article_id", "article_read_states", ["article_id"])
    sources = sa.table("sources", sa.column("id", sa.Integer()))
    articles = sa.table(
        "articles", sa.column("id", sa.Integer()), sa.column("is_read", sa.Boolean())
    )
    owner = sa.literal(OWNER, type_=sa.Uuid())
    op.execute(
        subscriptions.insert().from_select(["user_id", "source_id"], sa.select(owner, sources.c.id))
    )
    op.execute(
        reads.insert().from_select(
            ["user_id", "article_id"],
            sa.select(owner, articles.c.id).where(articles.c.is_read.is_(True)),
        )
    )
    # SQLite >= 3.35 supports native DROP COLUMN: no table rebuild or FK cascade.
    op.drop_column("articles", "is_read")
    if op.get_bind().dialect.name == "postgresql":
        for table in ("app_users", "subscriptions", "article_read_states"):
            op.execute(f"REVOKE ALL ON tnr.{table} FROM PUBLIC")
        op.execute("""
            DO $$
            DECLARE api_role text;
            BEGIN
                FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                        EXECUTE format(
                            'REVOKE ALL ON tnr.app_users, tnr.subscriptions, '
                            'tnr.article_read_states FROM %I', api_role
                        );
                    END IF;
                END LOOP;
            END $$
        """)


def downgrade() -> None:
    # A single-user schema can retain only the reserved owner's read flags.
    op.add_column(
        "articles", sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    articles = sa.table(
        "articles", sa.column("id", sa.Integer()), sa.column("is_read", sa.Boolean())
    )
    reads = sa.table(
        "article_read_states",
        sa.column("user_id", sa.Uuid()),
        sa.column("article_id", sa.Integer()),
    )
    op.execute(
        articles.update()
        .where(articles.c.id.in_(sa.select(reads.c.article_id).where(reads.c.user_id == OWNER)))
        .values(is_read=True)
    )
    op.drop_table("article_read_states")
    op.drop_table("subscriptions")
    op.drop_table("app_users")
