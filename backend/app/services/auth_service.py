"""
RouteCare AI - Authentication business logic.

Kept separate from app/modules/auth/router.py so the HTTP layer stays
thin and this logic is reusable/testable without spinning up FastAPI.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, ConflictError, UnauthorizedError
from app.core.logging_config import auth_logger
from app.core.permissions import UserRole
from app.core.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.clinic import Clinic
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User

INVALID_CREDENTIALS = UnauthorizedError("Invalid email or password.", code="INVALID_CREDENTIALS")
INVALID_REFRESH_TOKEN = UnauthorizedError(
    "Refresh token is invalid, expired, or revoked.", code="INVALID_REFRESH_TOKEN"
)
INVALID_RESET_TOKEN = BusinessRuleError("Reset token is invalid or expired.", code="INVALID_RESET_TOKEN")

# Precomputed once so a "user not found" login attempt still pays the
# cost of a bcrypt comparison, keeping response timing close to the
# "user found, wrong password" path and reducing user-enumeration risk.
_DUMMY_PASSWORD_HASH = hash_password("timing-attack-mitigation-dummy-value")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(dt: datetime) -> datetime:
    """
    Normalize a datetime read back from the DB to timezone-aware UTC.

    SQLite (used in tests) silently drops tzinfo on round-trip even for
    a DateTime(timezone=True) column; every datetime this app writes is
    already UTC, so a naive value read back is safely assumed to be UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _log_audit(db: Session, *, clinic_id, user_id, action: str) -> None:
    db.add(AuditLog(clinic_id=clinic_id, user_id=user_id, action=action, entity_type="USER", entity_id=user_id))


def register_clinic_and_admin(
    db: Session, *, clinic_name: str, first_name: str, last_name: str, email: str, password: str
) -> User:
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        raise ConflictError("An account with that email already exists.", code="EMAIL_ALREADY_EXISTS")

    clinic = Clinic(name=clinic_name)
    db.add(clinic)
    db.flush()  # assign clinic.id without committing

    user = User(
        clinic_id=clinic.id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=hash_password(password),
        role=UserRole.CLINIC_ADMIN,
        is_active=True,
    )
    db.add(user)
    db.flush()

    _log_audit(db, clinic_id=clinic.id, user_id=user.id, action="USER_REGISTERED")
    db.commit()
    db.refresh(user)

    auth_logger.info("user_registered", extra={"user_id": str(user.id), "clinic_id": str(clinic.id)})
    return user


def _issue_token_pair(db: Session, user: User) -> tuple[str, str]:
    access_token = create_access_token(
        {
            "sub": str(user.id),
            "user_id": str(user.id),
            "clinic_id": str(user.clinic_id) if user.clinic_id else None,
            "role": user.role.value,
        }
    )

    raw_refresh_token = generate_secure_token()
    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh_token),
        expires_at=_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(refresh_token)
    db.commit()

    return access_token, raw_refresh_token


def authenticate_user(
    db: Session, *, email: str, password: str, ip_address: str | None = None
) -> tuple[User, str, str]:
    user = db.query(User).filter(User.email == email).first()

    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)  # burn equivalent time
        auth_logger.warning("login_failed", extra={"email": email, "reason": "no_such_user", "ip": ip_address})
        raise INVALID_CREDENTIALS

    if not verify_password(password, user.password_hash) or not user.is_active:
        _log_audit(db, clinic_id=user.clinic_id, user_id=user.id, action="LOGIN_FAILED")
        db.commit()
        auth_logger.warning("login_failed", extra={"user_id": str(user.id), "ip": ip_address})
        raise INVALID_CREDENTIALS

    user.last_login = _now()
    _log_audit(db, clinic_id=user.clinic_id, user_id=user.id, action="LOGIN_SUCCESS")

    access_token, raw_refresh_token = _issue_token_pair(db, user)
    db.refresh(user)

    auth_logger.info("login_success", extra={"user_id": str(user.id), "ip": ip_address})
    return user, access_token, raw_refresh_token


def refresh_access_token(db: Session, *, raw_refresh_token: str) -> tuple[User, str, str]:
    token_hash = hash_token(raw_refresh_token)
    token_row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if token_row is None:
        raise INVALID_REFRESH_TOKEN

    if token_row.revoked_at is not None:
        # Reuse of an already-rotated-out token: treat as a possible
        # theft/replay and invalidate every session for this user.
        _revoke_all_refresh_tokens(db, user_id=token_row.user_id)
        auth_logger.warning("refresh_token_reuse_detected", extra={"user_id": str(token_row.user_id)})
        raise INVALID_REFRESH_TOKEN

    if _aware_utc(token_row.expires_at) < _now():
        raise INVALID_REFRESH_TOKEN

    user = db.get(User, token_row.user_id)
    if user is None or not user.is_active:
        raise INVALID_REFRESH_TOKEN

    token_row.revoked_at = _now()
    access_token, raw_new_refresh_token = _issue_token_pair(db, user)

    auth_logger.info("token_refreshed", extra={"user_id": str(user.id)})
    return user, access_token, raw_new_refresh_token


def logout(db: Session, *, raw_refresh_token: str) -> None:
    token_hash = hash_token(raw_refresh_token)
    token_row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if token_row is not None and token_row.revoked_at is None:
        token_row.revoked_at = _now()
        _log_audit(db, clinic_id=None, user_id=token_row.user_id, action="LOGOUT")
        db.commit()
        auth_logger.info("logout", extra={"user_id": str(token_row.user_id)})
    # Logging out with an already-revoked/unknown token is still a no-op
    # success from the client's point of view - there is nothing left to revoke.


def _revoke_all_refresh_tokens(db: Session, *, user_id: uuid.UUID) -> None:
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)).update(
        {"revoked_at": _now()}
    )
    db.commit()


def change_password(db: Session, *, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise UnauthorizedError("Current password is incorrect.", code="INVALID_CREDENTIALS")

    user.password_hash = hash_password(new_password)
    _revoke_all_refresh_tokens(db, user_id=user.id)
    _log_audit(db, clinic_id=user.clinic_id, user_id=user.id, action="PASSWORD_CHANGED")
    db.commit()

    auth_logger.info("password_changed", extra={"user_id": str(user.id)})


def request_password_reset(db: Session, *, email: str) -> str | None:
    """
    Always behaves the same from the caller's perspective regardless of
    whether the email exists, to avoid user enumeration. Returns the raw
    reset token only so the router can decide whether to expose it (dev
    convenience until real email delivery exists) - callers must not log it.
    """
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        auth_logger.info("password_reset_requested", extra={"email": email, "user_found": False})
        return None

    raw_token = generate_secure_token()
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=_now() + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
    )
    db.add(reset_token)
    _log_audit(db, clinic_id=user.clinic_id, user_id=user.id, action="PASSWORD_RESET_REQUESTED")
    db.commit()

    auth_logger.info("password_reset_requested", extra={"user_id": str(user.id), "user_found": True})
    # TODO(email): send raw_token via an email delivery service instead of
    # returning it to the caller once one is integrated.
    return raw_token


def reset_password(db: Session, *, raw_token: str, new_password: str) -> None:
    token_hash = hash_token(raw_token)
    token_row = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()

    if token_row is None or token_row.used_at is not None or _aware_utc(token_row.expires_at) < _now():
        raise INVALID_RESET_TOKEN

    user = db.get(User, token_row.user_id)
    if user is None or not user.is_active:
        raise INVALID_RESET_TOKEN

    user.password_hash = hash_password(new_password)
    token_row.used_at = _now()
    _revoke_all_refresh_tokens(db, user_id=user.id)
    _log_audit(db, clinic_id=user.clinic_id, user_id=user.id, action="PASSWORD_RESET_COMPLETED")
    db.commit()

    auth_logger.info("password_reset_completed", extra={"user_id": str(user.id)})
