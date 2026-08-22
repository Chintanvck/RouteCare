"""
RouteCare AI - ORM models.

Every model module is imported here so it registers with
`app.database.base.Base.metadata` as soon as this package is imported -
required for both Alembic autogenerate and `Base.metadata.create_all()`
in tests.
"""

from app.models.audit_log import AuditLog
from app.models.clinic import Clinic
from app.models.password_reset_token import PasswordResetToken
from app.models.patient import Patient
from app.models.refresh_token import RefreshToken
from app.models.user import User

__all__ = [
    "AuditLog",
    "Clinic",
    "PasswordResetToken",
    "Patient",
    "RefreshToken",
    "User",
]
