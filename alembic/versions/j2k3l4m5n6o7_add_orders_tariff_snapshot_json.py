from alembic import op

# revision identifiers, used by Alembic.
revision = "j2k3l4m5n6o7"
down_revision = "h1i2j3k4l5m6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS tariff_snapshot_json JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS tariff_snapshot_json")
