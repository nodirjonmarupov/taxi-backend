"""Add orders.pause_started_ts for DB mirror of manual pause (billing fallback).

Revision ID: p6q7r8s9t0u1
Revises: n5o6p7q8r9s0
Create Date: 2026-05-03
"""

from alembic import op


revision = "p6q7r8s9t0u1"
down_revision = "n5o6p7q8r9s0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS pause_started_ts "
        "DOUBLE PRECISION NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS pause_started_ts")
