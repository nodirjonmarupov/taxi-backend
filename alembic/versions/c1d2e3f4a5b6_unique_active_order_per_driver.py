"""Add unique constraint: one driver can have at most one active (accepted/in_progress) order.

Revision ID: c1d2e3f4a5b6
Revises: b0c8f2d4e3a1
Create Date: 2025-03-16

"""
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b0c8f2d4e3a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX idx_driver_one_active_order
        ON orders (driver_id)
        WHERE driver_id IS NOT NULL
          AND status IN ('accepted', 'in_progress');
    """)


def downgrade() -> None:
    op.drop_index("idx_driver_one_active_order", table_name="orders")
