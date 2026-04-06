"""
Add Bonus System
Cashback (EARN) va Redeem (SPEND) tizimi uchun schema.
"""

from alembic import op

# Revision identifiers, used by Alembic.
revision = "g7h8i9j0k1l2"
down_revision = "f2a6f6d4c7b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users: bonus balance
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS"
        " bonus_balance NUMERIC(10,2) NOT NULL DEFAULT 0"
    )

    # Orders: redeem flags/amount
    op.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS"
        " is_bonus_requested BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS"
        " used_bonus NUMERIC(10,2) NOT NULL DEFAULT 0"
    )

    # Bonus transactions table
    op.execute("""
        CREATE TABLE IF NOT EXISTS bonus_transactions (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
            order_id    INTEGER NOT NULL REFERENCES orders(id)  ON DELETE CASCADE,
            transaction_type VARCHAR(10) NOT NULL,
            amount      NUMERIC(10,2) NOT NULL,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    # Index that op.create_table would have created via index=True on transaction_type
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_bonus_transactions_transaction_type"
        " ON bonus_transactions (transaction_type)"
    )

    # Settings: cashback/redeem parameters
    op.execute(
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS"
        " cashback_percent FLOAT NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS"
        " max_bonus_usage_percent FLOAT NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bonus_transactions")

    op.execute("ALTER TABLE settings DROP COLUMN IF EXISTS max_bonus_usage_percent")
    op.execute("ALTER TABLE settings DROP COLUMN IF EXISTS cashback_percent")

    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS used_bonus")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS is_bonus_requested")

    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS bonus_balance")
