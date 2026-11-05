"""Create the news schema and initial editable categories.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.UniqueConstraint("name", name="uq_categories_name"),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_categories_name_not_blank")),
        sa.CheckConstraint("length(trim(slug)) > 0", name=op.f("ck_categories_slug_not_blank")),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("feed_url", sa.String(2048), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("refresh_interval_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("feed_url", name="uq_sources_feed_url"),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_sources_name_not_blank")),
        sa.CheckConstraint(
            "length(trim(feed_url)) > 0", name=op.f("ck_sources_feed_url_not_blank")
        ),
        sa.CheckConstraint(
            "refresh_interval_minutes > 0", name=op.f("ck_sources_positive_refresh_interval")
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0", name=op.f("ck_sources_nonnegative_failures")
        ),
    )
    op.create_index("ix_sources_category_id", "sources", ["category_id"])
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("guid", sa.String(1024), nullable=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_id", "guid", name="uq_articles_source_guid"),
        sa.UniqueConstraint("source_id", "url", name="uq_articles_source_url"),
        sa.CheckConstraint(
            "guid IS NULL OR length(trim(guid)) > 0", name=op.f("ck_articles_guid_not_blank")
        ),
        sa.CheckConstraint("length(trim(url)) > 0", name=op.f("ck_articles_url_not_blank")),
        sa.CheckConstraint("length(trim(title)) > 0", name=op.f("ck_articles_title_not_blank")),
    )
    op.create_index("ix_articles_published_at", "articles", ["published_at", "id"])
    op.create_index(
        "ix_articles_source_published_at", "articles", ["source_id", "published_at", "id"]
    )
    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(20), server_default="running", nullable=False),
        sa.Column("articles_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("articles_added", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'not_modified', 'error')",
            name=op.f("ck_collection_runs_valid_status"),
        ),
        sa.CheckConstraint("articles_seen >= 0", name=op.f("ck_collection_runs_nonnegative_seen")),
        sa.CheckConstraint(
            "articles_added >= 0 AND articles_added <= articles_seen",
            name=op.f("ck_collection_runs_valid_added"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_collection_runs_valid_finish_time"),
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL) OR "
            "(status <> 'running' AND finished_at IS NOT NULL)",
            name=op.f("ck_collection_runs_status_matches_finish"),
        ),
    )
    op.create_index(
        "ix_collection_runs_source_started_at", "collection_runs", ["source_id", "started_at", "id"]
    )
    op.bulk_insert(
        categories,
        [
            {"name": name, "slug": slug, "sort_order": position}
            for position, (name, slug) in enumerate(
                [
                    ("Artificial intelligence and LLMs", "artificial-intelligence"),
                    ("AI agents and agentic development", "ai-agents"),
                    ("Software engineering", "software-engineering"),
                    ("Open-weight and open-source models", "open-models"),
                    ("Technology companies", "technology-companies"),
                    ("Research and scientific publications", "research"),
                    ("Economics and financial markets", "economics-finance"),
                    ("International technology news", "international-tech"),
                ]
            )
        ],
    )


def downgrade() -> None:
    op.drop_table("collection_runs")
    op.drop_table("articles")
    op.drop_table("sources")
    op.drop_table("categories")
