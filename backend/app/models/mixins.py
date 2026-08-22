"""
RouteCare AI - Reusable model mixins.

Per docs/04_Database_Design.md sections 1.2/1.3, most future business
tables need created_at/updated_at, and soft-deletable ones also need
deleted_at. New domain models (Patient, Appointment, Therapist, ...)
should inherit these from the start:

    class Patient(Base, TimestampMixin, SoftDeleteMixin):
        __tablename__ = "patients"
        id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
        ...

Not applied retroactively to Clinic/User (Phase 1A/1B, already
reviewed) - there's no functional difference between their hand-written
columns and what these mixins would generate, so retrofitting them
would just be churn on already-validated code.
"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
