"""
RouteCare AI - Therapist availability model.

Per docs/04_Database_Design.md section 6. Recurring weekly pattern only
- no date-specific overrides (holidays, one-off days off) since the
doc's schema has no column for that and the task explicitly says not
to build complex recurring-calendar support beyond what's required.

`day_of_week` uses Python's `date.weekday()` convention: 0=Monday,
6=Sunday. Documented here because the design doc doesn't pick one and
frontend/backend must agree on it exactly.

A day is "unavailable" simply by having no rows for that day_of_week -
no explicit flag needed. `is_available=False` rows are for breaks
*within* an otherwise-working day (e.g. Monday 08:00-12:00 available,
12:00-13:00 not available, 13:00-17:00 available) - not for whole days
off, which are already covered by omission.
"""

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import GUID


class TherapistAvailability(Base):
    __tablename__ = "therapist_availability"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    therapist_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("therapists.id"), nullable=False, index=True)

    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
