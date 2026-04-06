from alembic import op

# revision identifiers, used by Alembic.
revision = "b0c8f2d4e3a1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure PostGIS is available
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    # Geography(Point, 4326) for fast radius search — idempotent
    op.execute(
        "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS"
        " location geography(POINT,4326)"
    )
    op.execute(
        "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS"
        " location_updated_at TIMESTAMP"
    )

    # Backfill location from existing lat/lon (already idempotent — UPDATE is safe to re-run)
    op.execute(
        """
        UPDATE drivers
        SET
            location = ST_SetSRID(ST_MakePoint(current_longitude, current_latitude), 4326)::geography,
            location_updated_at = updated_at
        WHERE current_latitude  IS NOT NULL
          AND current_longitude IS NOT NULL;
        """
    )

    # GIST index is required for ST_DWithin performance with geography — idempotent
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_drivers_location_gist"
        " ON drivers USING GIST (location)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_drivers_location_gist")
    op.execute("ALTER TABLE drivers DROP COLUMN IF EXISTS location_updated_at")
    op.execute("ALTER TABLE drivers DROP COLUMN IF EXISTS location")
