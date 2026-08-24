"""add geocoding status fields to patients and therapists

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-23

Phase 5 (Maps & Travel-Time Engine): adds geocoding_status/geocoded_at/
location_verified to `patients` and `therapists`, per
app.models.patient.GeocodingStatus's docstring. No new tables - travel
time results are cached in Redis (app.services.travel_time_service),
not persisted, so there's nothing to migrate for those.

Existing rows that already have coordinates (set manually, or via
Phase 2/3 before real geocoding existed) are backfilled as GEOCODED +
location_verified=true - they were presumably entered/reviewed by a
human already, so treat them as trustworthy rather than re-geocoding
out from under them the first time this code runs.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_GEOCODING_STATUS = postgresql.ENUM("PENDING", "GEOCODED", "FAILED", "MANUAL", name="geocoding_status")


def upgrade() -> None:
    bind = op.get_bind()
    _GEOCODING_STATUS.create(bind, checkfirst=True)

    for table, lat_col, lng_col in (
        ("patients", "latitude", "longitude"),
        ("therapists", "home_latitude", "home_longitude"),
    ):
        op.add_column(
            table,
            sa.Column(
                "geocoding_status",
                postgresql.ENUM("PENDING", "GEOCODED", "FAILED", "MANUAL", name="geocoding_status", create_type=False),
                nullable=False,
                server_default="PENDING",
            ),
        )
        op.add_column(table, sa.Column("geocoded_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("location_verified", sa.Boolean(), nullable=False, server_default=sa.false()))

        op.execute(
            f"UPDATE {table} SET geocoding_status = 'GEOCODED', location_verified = true, "
            f"geocoded_at = updated_at WHERE {lat_col} IS NOT NULL AND {lng_col} IS NOT NULL"
        )


def downgrade() -> None:
    for table in ("patients", "therapists"):
        op.drop_column(table, "location_verified")
        op.drop_column(table, "geocoded_at")
        op.drop_column(table, "geocoding_status")

    _GEOCODING_STATUS.drop(op.get_bind(), checkfirst=True)
