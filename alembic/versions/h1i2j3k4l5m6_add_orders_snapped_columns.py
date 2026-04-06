from alembic import op

# revision identifiers, used by Alembic.
revision = "h1i2j3k4l5m6"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Snapped driver coordinates stored per-order so the user tracking page
    # can display the road-aligned position without recomputing on the client.
    op.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS snapped_lat DOUBLE PRECISION"
    )
    op.execute(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS snapped_lon DOUBLE PRECISION"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS snapped_lon")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS snapped_lat")
