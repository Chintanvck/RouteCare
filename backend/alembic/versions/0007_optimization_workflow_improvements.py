"""optimization workflow improvements: weekly mode, per-recommendation accept/reject, marginal fields

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-25

Phase 7. See app/models/optimization.py's docstring for the full
reasoning behind each change:

- `optimization_mode` gains a new enum value `WEEK_SCHEDULE_OPTIMIZATION`.
  Postgres allows `ALTER TYPE ... ADD VALUE` inside a transaction as of
  PG12+ as long as the new value isn't *used* in the same transaction
  (it isn't here) - safe on this project's PG16.
- `optimization_recommendations` gains `target_date` (which calendar day
  this recommendation covers - required so weekly mode's 7 per-day rows
  are distinguishable), `accepted_at`/`rejected_at` (acceptance state
  moves from the request to the recommendation itself), and
  `marginal_drive_minutes`/`marginal_distance_miles` (NEW_PATIENT_PLACEMENT's
  insertion-specific cost, now separate from `total_drive_minutes`, which
  is fixed to mean "the day's full total" consistently across all modes).
- `optimization_requests.accepted_recommendation_id` is dropped - not a
  real FK to begin with (Phase 6 documented why), and superseded by
  per-recommendation `accepted_at`.

Existing recommendation rows (from Phase 6) get their `target_date`
backfilled from their parent request's `target_date` - true for every
row created so far, since weekly mode (the only case where a
recommendation's date can differ from its request's) didn't exist yet.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE optimization_mode ADD VALUE IF NOT EXISTS 'WEEK_SCHEDULE_OPTIMIZATION'")

    op.add_column("optimization_recommendations", sa.Column("target_date", sa.Date(), nullable=True))
    op.execute(
        "UPDATE optimization_recommendations SET target_date = "
        "(SELECT target_date FROM optimization_requests WHERE optimization_requests.id = "
        "optimization_recommendations.optimization_request_id)"
    )
    op.alter_column("optimization_recommendations", "target_date", nullable=False)

    op.add_column("optimization_recommendations", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("optimization_recommendations", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("optimization_recommendations", sa.Column("marginal_drive_minutes", sa.Integer(), nullable=True))
    op.add_column("optimization_recommendations", sa.Column("marginal_distance_miles", sa.Numeric(7, 2), nullable=True))

    op.drop_column("optimization_requests", "accepted_recommendation_id")


def downgrade() -> None:
    op.add_column(
        "optimization_requests", sa.Column("accepted_recommendation_id", postgresql.UUID(as_uuid=True), nullable=True)
    )

    op.drop_column("optimization_recommendations", "marginal_distance_miles")
    op.drop_column("optimization_recommendations", "marginal_drive_minutes")
    op.drop_column("optimization_recommendations", "rejected_at")
    op.drop_column("optimization_recommendations", "accepted_at")
    op.drop_column("optimization_recommendations", "target_date")

    # Postgres has no "remove enum value" - WEEK_SCHEDULE_OPTIMIZATION stays defined but unused
    # if this migration is rolled back. Not a functional problem (nothing reads/writes it once
    # the application code is also reverted alongside this migration).
