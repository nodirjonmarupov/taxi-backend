from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography

# revision identifiers, used by Alembic.
revision = "b0c8f2d4e3a1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure PostGIS is available
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    # Geography(Point, 4326) for fast radius search
    op.add_column(
        "drivers",
        sa.Column(
            "location",
            Geography(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
    )
    op.add_column(
        "drivers",
        sa.Column(
            "location_updated_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    # Backfill location from existing lat/lon (location_updated_at set from updated_at)
    op.execute(
        """
        UPDATE drivers
        SET
            location = ST_SetSRID(ST_MakePoint(current_longitude, current_latitude), 4326)::geography,
            location_updated_at = updated_at
        WHERE current_latitude IS NOT NULL
          AND current_longitude IS NOT NULL;
        """
    )

    # GIST index is required for ST_DWithin performance with geography
    op.create_index(
        "idx_drivers_location_gist",
        "drivers",
        ["location"],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("idx_drivers_location_gist", table_name="drivers")
    op.drop_column("drivers", "location_updated_at")
    op.drop_column("drivers", "location")
