"""Store article discussion links separately from descriptions."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("discussion_url", sa.Text(), nullable=True))
    # Old descriptions have already lost their link. Clear only the known placeholder.
    op.execute("""UPDATE articles SET description = NULL WHERE description = 'Comments'
        AND source_id IN (SELECT id FROM sources
            WHERE feed_url = 'https://news.ycombinator.com/rss')""")
    # Ask for a full feed on the next normal collection to enrich existing articles.
    op.execute("""UPDATE sources SET etag = NULL, last_modified = NULL
        WHERE feed_url = 'https://news.ycombinator.com/rss'""")


def downgrade() -> None:
    op.drop_column("articles", "discussion_url")
