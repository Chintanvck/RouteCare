"""
RouteCare AI - Shared request-scoped dependencies.

`get_current_user` and `get_current_clinic_id` are the two primitives
every future authenticated endpoint should depend on, so identity and
tenant resolution never gets re-implemented per module.
"""

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.request_context import clinic_id_var, user_id_var
from app.core.security import decode_access_token
from app.database.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the caller's User from the Authorization: Bearer <access_token> header."""
    unauthorized = UnauthorizedError("Not authenticated.")

    if credentials is None:
        raise unauthorized

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise unauthorized

    user_id_raw = payload.get("user_id")
    if not user_id_raw:
        raise unauthorized

    try:
        user_id = uuid.UUID(str(user_id_raw))
    except ValueError:
        raise unauthorized from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized

    # Make identity available to structured logging (see app.core.logging_config)
    # for the rest of this request without threading it through every call.
    user_id_var.set(str(user.id))
    clinic_id_var.set(str(user.clinic_id) if user.clinic_id else None)

    return user


def get_current_clinic_id(current_user: User = Depends(get_current_user)) -> uuid.UUID:
    """
    Resolve the caller's clinic. Raises 403 for platform-level users
    (SYSTEM_ADMIN) with no clinic_id attempting a clinic-scoped action.
    """
    if current_user.clinic_id is None:
        raise ForbiddenError("This action requires a clinic context.", code="NO_CLINIC_CONTEXT")
    return current_user.clinic_id
