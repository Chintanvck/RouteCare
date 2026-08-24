"""
RouteCare AI - Patient availability model.

Per docs/04_Database_Design.md section 8. Same day_of_week convention
as TherapistAvailability (0=Monday, 6=Sunday).

Unlike therapist availability (unconfigured day = unavailable),
an unconfigured patient (no rows at all) is treated as available
anytime - many homecare patients have broad, unstructured availability
and forcing them to enumerate it would just be friction with no
scheduling value. Rows only ever add constraints:
NOT_AVAILABLE rows block a window, PREFERRED/AVAILABLE rows (when any
exist for a day) restrict scheduling to within them.
"""

import uuid
from datetime import datetime, time
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, Time, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import GUID


class PatientAvailabilityPreference(str, Enum):
    PREFERRED = "PREFERRED"
    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class PatientAvailability(Base):
    __tablename__ = "patient_availability"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("patients.id"), nullable=False, index=True)

    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    preference_type: Mapped[PatientAvailabilityPreference] = mapped_column(
        SAEnum(PatientAvailabilityPreference, name="patient_availability_preference"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
