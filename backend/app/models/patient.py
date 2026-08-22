"""
RouteCare AI - Patient model.

Per docs/04_Database_Design.md section 7. This is scheduling-related
patient information only - explicitly NOT a clinical record system, per
the doc's own note. No medical/clinical fields belong here.

Unlike User (whose clinic_id is nullable for SYSTEM_ADMIN), a patient
always belongs to exactly one clinic - clinic_id is required.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import GUID
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class Patient(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clinics.id"), nullable=False, index=True)

    external_patient_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    address_line_1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    visit_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduling_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Where this record came from - "manual" for records created through
    # this API; Phase 3's Excel import will stamp its own source value.
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def is_active(self) -> bool:
        """Convenience for API responses - the DB has no separate active flag, only deleted_at."""
        return not self.is_deleted
