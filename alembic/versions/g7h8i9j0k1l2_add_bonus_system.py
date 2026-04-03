"""
Add Bonus System
Cashback (EARN) va Redeem (SPEND) tizimi uchun schema.
"""

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = "g7h8i9j0k1l2"
down_revision = "f2a6f6d4c7b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users: bonus balance
    op.add_column(
        "users",
        sa.Column(
            "bonus_balance",
            sa.Numeric(10, 2),
            server_default="0",
            nullable=False,
        ),
    )

    # Orders: redeem flags/amount
    op.add_column(
        "orders",
        sa.Column(
            "is_bonus_requested",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "used_bonus",
            sa.Numeric(10, 2),
            server_default="0",
            nullable=False,
        ),
    )

    # Bonus transactions
    op.create_table(
        "bonus_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transaction_type", sa.String(length=10), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Settings: cashback/redeem parameters
    op.add_column(
        "settings",
        sa.Column(
            "cashback_percent",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "max_bonus_usage_percent",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("bonus_transactions")

    op.drop_column("settings", "max_bonus_usage_percent")
    op.drop_column("settings", "cashback_percent")

    op.drop_column("orders", "used_bonus")
    op.drop_column("orders", "is_bonus_requested")

    op.drop_column("users", "bonus_balance")

