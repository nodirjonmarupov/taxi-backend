"""Add orders.waiting_seconds for Redis-missing billing fallback.

Revision ID: m4n5o6p7q8r9
Revises: k3l4m5n6o7p8
Create Date: 2026-04-23
"""

from alembic import op

revision = "m4n5o6p7q8r9"
down_revision = "k3l4m5n6o7p8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS waiting_seconds "
        "DOUBLE PRECISION NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS waiting_seconds")
