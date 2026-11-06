"""Explicit Supabase identity links for approved application users.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No Auth schema FK: the application also runs on an independent SQLite database.
    # Existing users remain unlinked until an operator approves the exact identity.
    op.add_column("app_users", sa.Column("supabase_subject", sa.Uuid(), nullable=True))
    op.create_index("ix_app_users_supabase_subject", "app_users", ["supabase_subject"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_app_users_supabase_subject", table_name="app_users")
    op.drop_column("app_users", "supabase_subject")
