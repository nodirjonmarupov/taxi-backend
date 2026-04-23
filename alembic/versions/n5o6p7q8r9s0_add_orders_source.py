"""Add orders.source for manual taximeter trips (skip customer Telegram).

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-04-24

"""
import sqlalchemy as sa
from alembic import op

revision = "n5o6p7q8r9s0"
down_revision = "m4n5o6p7q8r9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("source", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "source")
