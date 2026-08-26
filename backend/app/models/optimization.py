"""
RouteCare AI - Schedule optimization models.

Per docs/04_Database_Design.md sections 11-12, extended with the fields
actually needed to run the three optimization modes this phase
implements (see app/services/optimization_engine.py for the algorithms):

- `mode` distinguishes DAY_SCHEDULE_OPTIMIZATION (re-order one
  therapist's existing day), NEW_PATIENT_PLACEMENT (find a slot for one
  not-yet-scheduled patient), and WEEK_SCHEDULE_OPTIMIZATION (Phase 7 -
  runs DAY_SCHEDULE_OPTIMIZATION's own logic once per day of the week
  and stores one recommendation per day) - the design doc's table has no
  such column, but a request is meaningless without knowing which
  problem it solves.
- `target_date`/`search_days`/`new_patient_id`/`new_appointment_duration_minutes`
  hold each mode's own inputs. All four are nullable since only one
  mode's fields apply to any given row. For WEEK_SCHEDULE_OPTIMIZATION,
  `target_date` is any date in the target week - the service snaps it to
  that week's Monday.

Acceptance state (Phase 7) lives on OptimizationRecommendation itself
(`accepted_at`/`rejected_at`), not as a single back-reference from the
request as Phase 6 originally had it (`accepted_recommendation_id`,
removed in migration 0007). Two reasons: (1) weekly mode needs
*independent* per-day acceptance - a single slot on the request can't
represent "Monday accepted, Tuesday rejected, Wednesday still pending"
- and (2) it removes the circular-FK question Phase 6's docstring
flagged, rather than answering it with a real FK: recommendations no
longer need any reference back to the request beyond the existing
one-directional `optimization_request_id` FK they already have.
`app/services/optimization_service.accept_recommendation` still
prevents accepting two *competing* recommendations for the same
decision (only relevant for NEW_PATIENT_PLACEMENT, where up to 3
ranked alternatives all propose scheduling the same not-yet-booked
patient - day/week recommendations never compete with each other by
construction, one per date).

Recommendations never store more patient-sensitive data than an
appointment already exposes (IDs, times, computed metrics) -
`recommendation_data` holds only what's needed to replay the proposal
through the existing, already-validated appointment_service functions
on accept (see app/services/optimization_service.py), never raw
addresses or notes.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import GUID
from app.models.mixins import TimestampMixin

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class OptimizationMode(str, Enum):
    DAY_SCHEDULE_OPTIMIZATION = "DAY_SCHEDULE_OPTIMIZATION"
    NEW_PATIENT_PLACEMENT = "NEW_PATIENT_PLACEMENT"
    WEEK_SCHEDULE_OPTIMIZATION = "WEEK_SCHEDULE_OPTIMIZATION"


class OptimizationStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OptimizationRequest(Base, TimestampMixin):
    __tablename__ = "optimization_requests"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clinics.id"), nullable=False, index=True)
    therapist_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("therapists.id"), nullable=False, index=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)

    mode: Mapped[OptimizationMode] = mapped_column(SAEnum(OptimizationMode, name="optimization_mode"), nullable=False)
    status: Mapped[OptimizationStatus] = mapped_column(
        SAEnum(OptimizationStatus, name="optimization_status"), nullable=False, default=OptimizationStatus.PENDING
    )

    # DAY_SCHEDULE_OPTIMIZATION: the day being re-ordered.
    # NEW_PATIENT_PLACEMENT: the start of the search window.
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    # NEW_PATIENT_PLACEMENT only - how many days forward from target_date to search.
    search_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_patient_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("patients.id"), nullable=True)
    new_appointment_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OptimizationRecommendation(Base):
    __tablename__ = "optimization_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    optimization_request_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("optimization_requests.id"), nullable=False, index=True
    )

    # Which calendar day this recommendation covers. Always equal to the parent request's own
    # target_date for DAY_SCHEDULE_OPTIMIZATION/NEW_PATIENT_PLACEMENT (candidate slots on
    # different days still all belong to one target-date *search window*); for
    # WEEK_SCHEDULE_OPTIMIZATION each of the week's 7 recommendation rows gets its own date -
    # this is precisely what lets the weekly view "clearly distinguish" one day from another.
    target_date: Mapped[date] = mapped_column(Date, nullable=False)

    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    efficiency_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    # The full day's total AFTER applying this recommendation, for every mode (Phase 7 fixed
    # NEW_PATIENT_PLACEMENT to report a true day total - baseline + marginal - here too, not just
    # the inserted visit's own marginal cost; see marginal_drive_minutes below).
    total_drive_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_distance_miles: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    time_saved_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    miles_saved: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    # NEW_PATIENT_PLACEMENT only - the portion of total_drive_minutes/total_distance_miles
    # specifically attributable to inserting this one new visit (vs. the day's pre-existing
    # baseline). Null for every other mode, where "marginal" isn't a meaningful concept.
    marginal_drive_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    marginal_distance_miles: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)

    reason_codes: Mapped[list[str]] = mapped_column(JSONVariant, nullable=False, default=list)
    explanation: Mapped[str] = mapped_column(Text(), nullable=False)
    # Proposal payload replayed through appointment_service on accept - shape depends on
    # OptimizationMode, see optimization_service.py's accept_recommendation docstring.
    recommendation_data: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False)

    solver_status: Mapped[str] = mapped_column(String(20), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
