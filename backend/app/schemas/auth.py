"""
RouteCare AI - Auth request/response schemas.
"""

import re
import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.permissions import UserRole

_UPPERCASE_RE = re.compile(r"[A-Z]")
_LOWERCASE_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")
_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 72  # bcrypt ignores bytes past 72; enforce here instead of truncating silently.


def validate_password_strength(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters long.")
    if not _UPPERCASE_RE.search(password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not _LOWERCASE_RE.search(password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not _DIGIT_RE.search(password):
        raise ValueError("Password must contain at least one number.")
    if not _SPECIAL_RE.search(password):
        raise ValueError("Password must contain at least one special character.")
    return password


class RegisterRequest(BaseModel):
    clinic_name: str = Field(min_length=1, max_length=255)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class RegisterResponse(BaseModel):
    message: str
    user_id: uuid.UUID


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserPublic(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    role: UserRole
    clinic_id: uuid.UUID | None
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class RequestPasswordResetRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class RequestPasswordResetResponse(BaseModel):
    message: str
    # Dev-only convenience field: populated only when ENVIRONMENT != "production",
    # since no email delivery service is integrated yet. See auth_service.request_password_reset.
    reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return validate_password_strength(v)
