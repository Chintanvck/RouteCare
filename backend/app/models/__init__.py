"""
RouteCare AI - ORM models.

Every model module is imported here so it registers with
`app.database.base.Base.metadata` as soon as this package is imported -
required for both Alembic autogenerate and `Base.metadata.create_all()`
in tests.
"""

from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.clinic import Clinic
from app.models.import_job import ImportJob
from app.models.import_row import ImportRow
from app.models.import_row_error import ImportRowError
from app.models.optimization import (
    OptimizationMode,
    OptimizationRecommendation,
    OptimizationRequest,
    OptimizationStatus,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.patient import GeocodingStatus, Patient
from app.models.patient_availability import PatientAvailability
from app.models.refresh_token import RefreshToken
from app.models.therapist import Therapist
from app.models.therapist_availability import TherapistAvailability
from app.models.user import User

__all__ = [
    "Appointment",
    "AuditLog",
    "Clinic",
    "ImportJob",
    "ImportRow",
    "ImportRowError",
    "GeocodingStatus",
    "OptimizationMode",
    "OptimizationRecommendation",
    "OptimizationRequest",
    "OptimizationStatus",
    "PasswordResetToken",
    "Patient",
    "PatientAvailability",
    "RefreshToken",
    "Therapist",
    "TherapistAvailability",
    "User",
]
