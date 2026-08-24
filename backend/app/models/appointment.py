"""
RouteCare AI - Appointment model.

Per docs/04_Database_Design.md section 9. `scheduled_date`/`start_time`/
`end_time` are naive DATE/TIME columns, exactly as specified - always
interpreted as wall-clock time in the owning Clinic's timezone
(`Clinic.timezone`, from Phase 1A), never hardcoded to any specific zone.
This isn't ambiguous in practice: every query is already clinic-scoped,
so there's never a cross-timezone comparison to get wrong - redesigning
these into TIMESTAMPTZ columns would be schema churn without a real
benefit at this stage. See docs/13_Coding_Standards.md-style reasoning
in the Phase 4 PR notes.

"Cancel" is a status transition (CANCELLED), not a delete - the row
stays for history/audit, matching the doc's own status enum rather than
adding a redundant deleted_at column.

appointment_source is always MANUAL in this phase - AI_RECOMMENDED is
reserved for the optimization engine (a later phase, explicitly out of
scope here).
"""

import uuid
from datetime import date, time
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, Time
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.types import GUID
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.therapist import Therapist


class AppointmentStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class AppointmentSource(str, Enum):
    MANUAL = "MANUAL"
    AI_RECOMMENDED = "AI_RECOMMENDED"


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("patients.id"), nullable=False, index=True)
    therapist_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("therapists.id"), nullable=False, index=True)

    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(AppointmentStatus, name="appointment_status"), nullable=False, default=AppointmentStatus.SCHEDULED
    )
    appointment_source: Mapped[AppointmentSource] = mapped_column(
        SAEnum(AppointmentSource, name="appointment_source"), nullable=False, default=AppointmentSource.MANUAL
    )
    created_by: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)

    patient: Mapped["Patient"] = relationship()
    therapist: Mapped["Therapist"] = relationship()

    @property
    def patient_name(self) -> str:
        return self.patient.full_name

    @property
    def therapist_name(self) -> str:
        return f"{self.therapist.first_name} {self.therapist.last_name}"
