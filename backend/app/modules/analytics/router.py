"""
RouteCare AI - Operational analytics/efficiency dashboard endpoints (Phase 8).

Every metric is computed server-side in app.services.analytics_service -
the frontend only ever renders numbers this module returns, per the
task's explicit "do not calculate important business metrics only in
the frontend."

RBAC mirrors app.modules.optimization.router's pattern exactly:
CLINIC_ADMIN/OFFICE_SCHEDULER see clinic-wide analytics (optionally
filtered to one therapist via `?therapist_id=`); THERAPIST is always
force-restricted to their own data via `restrict_to_therapist_id`,
regardless of what `?therapist_id=` says - the same
`_own_therapist_id_if_therapist` helper every other role-scoped module
already uses. SYSTEM_ADMIN has no clinic_id and is rejected by
get_current_clinic_id before reaching any of these - this phase adds no
platform-level analytics, per the task's explicit scope.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_clinic_id, get_current_user
from app.core.exceptions import NotFoundError
from app.core.permissions import UserRole, require_role
from app.database.session import get_db
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsOverview,
    DateRangeParams,
    EfficiencyMetrics,
    OptimizationImpact,
    TherapistAnalyticsResponse,
)
from app.services import analytics_service, therapist_service

router = APIRouter()

_ALLOWED_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER, UserRole.THERAPIST)


def _own_therapist_id_if_therapist(db: Session, *, clinic_id: uuid.UUID, current_user: User) -> uuid.UUID | None:
    """Mirrors app.modules.optimization.router's helper - the caller's own therapist_id to force
    every query to, or None for CLINIC_ADMIN/OFFICE_SCHEDULER (no restriction needed)."""
    if current_user.role != UserRole.THERAPIST:
        return None
    therapist = therapist_service.get_therapist_by_user_id(db, clinic_id=clinic_id, user_id=current_user.id)
    if therapist is None:
        raise NotFoundError("Therapist profile was not found.", code="THERAPIST_NOT_FOUND")
    return therapist.id


def _effective_therapist_id(restrict_to: uuid.UUID | None, requested: uuid.UUID | None) -> uuid.UUID | None:
    """Same precedence as appointment_service.list_appointments: a THERAPIST's own id always wins
    over whatever `?therapist_id=` was passed - it never widens their view, only a no-op if they
    happen to pass their own id."""
    return restrict_to if restrict_to is not None else requested


@router.get("/overview", response_model=AnalyticsOverview, dependencies=[Depends(require_role(*_ALLOWED_ROLES))])
def get_overview(
    date_range: DateRangeParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalyticsOverview:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    resolved_range = analytics_service.resolve_date_range(
        db, clinic_id=clinic_id, period=date_range.period, start_date=date_range.start_date, end_date=date_range.end_date
    )
    return analytics_service.compute_overview(db, clinic_id=clinic_id, date_range=resolved_range, therapist_id=restrict_to)


@router.get(
    "/therapists", response_model=TherapistAnalyticsResponse, dependencies=[Depends(require_role(*_ALLOWED_ROLES))]
)
def get_therapist_analytics(
    therapist_id: uuid.UUID | None = Query(None, description="Limit to one therapist."),
    date_range: DateRangeParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TherapistAnalyticsResponse:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    effective_therapist_id = _effective_therapist_id(restrict_to, therapist_id)
    resolved_range = analytics_service.resolve_date_range(
        db, clinic_id=clinic_id, period=date_range.period, start_date=date_range.start_date, end_date=date_range.end_date
    )
    return analytics_service.compute_therapist_metrics(
        db, clinic_id=clinic_id, date_range=resolved_range, therapist_id=effective_therapist_id
    )


@router.get("/efficiency", response_model=EfficiencyMetrics, dependencies=[Depends(require_role(*_ALLOWED_ROLES))])
def get_efficiency_metrics(
    therapist_id: uuid.UUID | None = Query(None, description="Limit to one therapist."),
    date_range: DateRangeParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EfficiencyMetrics:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    effective_therapist_id = _effective_therapist_id(restrict_to, therapist_id)
    resolved_range = analytics_service.resolve_date_range(
        db, clinic_id=clinic_id, period=date_range.period, start_date=date_range.start_date, end_date=date_range.end_date
    )
    return analytics_service.compute_efficiency(
        db, clinic_id=clinic_id, date_range=resolved_range, therapist_id=effective_therapist_id
    )


@router.get(
    "/optimization-impact", response_model=OptimizationImpact, dependencies=[Depends(require_role(*_ALLOWED_ROLES))]
)
def get_optimization_impact(
    therapist_id: uuid.UUID | None = Query(None, description="Limit to one therapist."),
    date_range: DateRangeParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptimizationImpact:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    effective_therapist_id = _effective_therapist_id(restrict_to, therapist_id)
    resolved_range = analytics_service.resolve_date_range(
        db, clinic_id=clinic_id, period=date_range.period, start_date=date_range.start_date, end_date=date_range.end_date
    )
    return analytics_service.compute_optimization_impact(
        db, clinic_id=clinic_id, date_range=resolved_range, therapist_id=effective_therapist_id
    )
