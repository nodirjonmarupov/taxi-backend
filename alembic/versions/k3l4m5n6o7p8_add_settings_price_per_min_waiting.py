from alembic import op

# revision identifiers, used by Alembic.
revision = "k3l4m5n6o7p8"
down_revision = "j2k3l4m5n6o7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS "
        "price_per_min_waiting NUMERIC(10,2) NOT NULL DEFAULT 500"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE settings DROP COLUMN IF EXISTS price_per_min_waiting")
