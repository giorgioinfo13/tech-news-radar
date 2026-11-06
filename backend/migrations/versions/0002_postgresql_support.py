"""Adapt PostgreSQL storage without changing existing SQLite data.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DATES = {
    "sources": ("last_checked_at", "last_success_at", "created_at"),
    "articles": ("published_at", "fetched_at"),
    "collection_runs": ("started_at", "finished_at"),
}
TEXT_COLUMNS = {
    "categories": {"name": 120, "slug": 120},
    "sources": {"name": 200, "feed_url": 2048},
    "articles": {"guid": 1024, "url": 2048, "title": None, "description": None},
}
KEYS = (
    ("sources", "uq_sources_feed_url", ("feed_url",)),
    ("articles", "uq_articles_source_guid", ("source_id", "guid")),
    ("articles", "uq_articles_source_url", ("source_id", "url")),
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, columns in DATES.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(timezone=True),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )
    for table, columns in TEXT_COLUMNS.items():
        for column, length in columns.items():
            kind = sa.Text(collation="C") if length is None else sa.String(length, collation="C")
            op.alter_column(table, column, type_=kind)
    for table, name, columns in KEYS:
        op.drop_constraint(name, table, type_="unique")
        expression = " || ':' || ".join(f"{column}::text" for column in columns)
        op.create_exclude_constraint(
            name, table, (sa.literal_column(f"({expression})"), "="), using="hash"
        )

    # No API role receives access, even if project-wide default grants exist.
    # Do not touch public/auth/storage or create roles in the Supabase project.
    op.execute("REVOKE ALL ON SCHEMA tnr FROM PUBLIC")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA tnr FROM PUBLIC")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA tnr FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE api_role text;
        BEGIN
            FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                    EXECUTE format('REVOKE ALL ON SCHEMA tnr FROM %I', api_role);
                    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA tnr FROM %I', api_role);
                    EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA tnr FROM %I', api_role);
                END IF;
            END LOOP;
        END $$
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, name, columns in KEYS:
        op.drop_constraint(name, table)
        # This can fail for long UTF-8 keys. The transaction preserves revision 0002.
        op.create_unique_constraint(name, table, list(columns))
    for table, columns in TEXT_COLUMNS.items():
        for column, length in columns.items():
            kind = (
                sa.Text(collation="default")
                if length is None
                else sa.String(length, collation="default")
            )
            op.alter_column(table, column, type_=kind)
    for table, columns in DATES.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )
    # Keep the namespace private on downgrade. Never restore Data API privileges.
