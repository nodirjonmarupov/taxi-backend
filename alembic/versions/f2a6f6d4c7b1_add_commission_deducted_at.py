"""Add commission_deducted_at to orders for commission idempotency.

Revision ID: f2a6f6d4c7b1
Revises: e8f9a0b1c2d3
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa


revision = "f2a6f6d4c7b1"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS commission_deducted_at TIMESTAMP NULL;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS commission_deducted_at;")

