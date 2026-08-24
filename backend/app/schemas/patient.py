"""
RouteCare AI - Patient request/response schemas.

Validation here covers structural/format checks (required fields, ZIP
format, phone format). It is deliberately not clinical-data validation
- docs/04_Database_Design.md section 7 is explicit that this table is
NOT a clinical record system.
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.patient import GeocodingStatus

_ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
_PHONE_RE = re.compile(r"^\+?[0-9()\-.\s]{7,20}$")
_STATE_RE = re.compile(r"^[A-Za-z]{2}$")


def _validate_zip(value: str) -> str:
    if not _ZIP_RE.match(value):
        raise ValueError("ZIP code must be in the form 12345 or 12345-6789.")
    return value


def _validate_phone(value: str) -> str:
    if not _PHONE_RE.match(value):
        raise ValueError("Phone number format is invalid.")
    return value


def _validate_state(value: str) -> str:
    if not _STATE_RE.match(value):
        raise ValueError("State must be a 2-letter abbreviation (e.g. NJ).")
    return value.upper()


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None

    address_line_1: str = Field(min_length=1, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str
    zip_code: str

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    external_patient_id: str | None = Field(default=None, max_length=100)
    visit_duration_minutes: int | None = Field(default=None, gt=0, le=480)
    priority_level: int | None = Field(default=None, ge=1, le=5)
    scheduling_notes: str | None = Field(default=None, max_length=2000)

    _validate_zip = field_validator("zip_code")(_validate_zip)
    _validate_state = field_validator("state")(_validate_state)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str | None) -> str | None:
        return _validate_phone(v) if v else v


class PatientUpdate(BaseModel):
    """All fields optional - PATCH semantics, only supplied fields are changed."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None

    address_line_1: str | None = Field(default=None, min_length=1, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = None
    zip_code: str | None = None

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_verified: bool | None = Field(
        default=None,
        description="Explicitly mark (or un-mark) this patient's coordinates as human-verified, "
        "without necessarily changing them - e.g. after visually confirming a map pin is correct.",
    )

    external_patient_id: str | None = Field(default=None, max_length=100)
    visit_duration_minutes: int | None = Field(default=None, gt=0, le=480)
    priority_level: int | None = Field(default=None, ge=1, le=5)
    scheduling_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("zip_code")
    @classmethod
    def _check_zip(cls, v: str | None) -> str | None:
        return _validate_zip(v) if v else v

    @field_validator("state")
    @classmethod
    def _check_state(cls, v: str | None) -> str | None:
        return _validate_state(v) if v else v

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str | None) -> str | None:
        return _validate_phone(v) if v else v


class PatientPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    external_patient_id: str | None
    first_name: str
    last_name: str
    phone: str | None
    email: str | None
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    zip_code: str
    latitude: float | None
    longitude: float | None
    geocoding_status: GeocodingStatus
    geocoded_at: datetime | None
    location_verified: bool
    visit_duration_minutes: int | None
    priority_level: int | None
    scheduling_notes: str | None
    source_system: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
