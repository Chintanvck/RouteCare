"""
RouteCare AI - Therapist request/response schemas.

Password/email validation is reused directly from the auth schemas
(app.schemas.auth) - a therapist's account is a User like any other,
so it needs the exact same password-strength rule, not a second copy.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.auth import validate_password_strength
from app.schemas.patient import _validate_phone


class TherapistCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str

    license_type: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    home_address: str | None = Field(default=None, max_length=2000)
    home_latitude: float | None = Field(default=None, ge=-90, le=90)
    home_longitude: float | None = Field(default=None, ge=-180, le=180)
    max_daily_hours: int | None = Field(default=None, gt=0, le=24)
    max_drive_time_minutes: int | None = Field(default=None, gt=0, le=600)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str | None) -> str | None:
        return _validate_phone(v) if v else v


class TherapistUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    is_active: bool | None = None

    license_type: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    home_address: str | None = Field(default=None, max_length=2000)
    home_latitude: float | None = Field(default=None, ge=-90, le=90)
    home_longitude: float | None = Field(default=None, ge=-180, le=180)
    max_daily_hours: int | None = Field(default=None, gt=0, le=24)
    max_drive_time_minutes: int | None = Field(default=None, gt=0, le=600)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else v

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str | None) -> str | None:
        return _validate_phone(v) if v else v


class TherapistPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    user_id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    is_active: bool
    license_type: str | None
    phone: str | None
    home_address: str | None
    home_latitude: float | None
    home_longitude: float | None
    max_daily_hours: int | None
    max_drive_time_minutes: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
