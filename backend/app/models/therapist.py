"""
RouteCare AI - Therapist model.

Per docs/04_Database_Design.md section 5. A Therapist is a profile
row 1:1 with a User (role=THERAPIST) - never a standalone account.
`user_id` is unique for exactly that reason: one therapist profile per
user, no duplicates.

Deactivation reuses `User.is_active` rather than adding a second active
flag here - a therapist profile has no independent "active" state from
its user account, and a second flag would just be one more place for
the two to drift out of sync.

`home_address` stays a single free-text field, matching the doc exactly
(unlike Patient, which splits address into structured lines/city/state/
zip) - geocoding isn't wired up for therapists in this phase either
(same as Patient's current no-op provider), so there's no need to force
a structure this phase doesn't use yet.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.types import GUID
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Therapist(Base, TimestampMixin):
    __tablename__ = "therapists"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clinics.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False, unique=True)

    license_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    home_address: Mapped[str | None] = mapped_column(Text(), nullable=True)
    home_latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    home_longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    max_daily_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_drive_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship()

    @property
    def first_name(self) -> str:
        return self.user.first_name

    @property
    def last_name(self) -> str:
        return self.user.last_name

    @property
    def email(self) -> str:
        return self.user.email

    @property
    def is_active(self) -> bool:
        return self.user.is_active
