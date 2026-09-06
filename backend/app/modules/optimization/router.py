"""
RouteCare AI - Schedule optimization endpoints.

Per docs/01_Product_Requirements_Document.md's role table: CLINIC_ADMIN
and OFFICE_SCHEDULER can run optimization for any therapist in the
clinic; THERAPIST can request optimization and accept/reject
recommendations for their own schedule only - enforced the same way
app.modules.scheduling.router restricts appointment access, via a
resolved `restrict_to_therapist_id`.

Creating a request only ever queues background work (see
app.workers.optimization_tasks) and returns immediately with
status=PENDING - the actual CP-SAT solve/insertion search never runs
inside this request/response cycle, per the explicit "do not block
normal HTTP requests" requirement.

POST /optimization/what-if is intentionally stateless - no
OptimizationRequest is created, nothing is persisted, per the What-If
foundation's "evaluate a hypothetical schedule without modifying the
real schedule" requirement.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_clinic_id, get_current_user
from app.core.exceptions import NotFoundError
from app.core.permissions import UserRole, require_role
from app.core.rate_limiting import rate_limit
from app.database.session import get_db
from app.models.user import User
from app.schemas.optimization import (
    AcceptRecommendationResponse,
    CreateOptimizationRequest,
    OptimizationRecommendationPublic,
    OptimizationRequestPublic,
    WhatIfApplyResponse,
    WhatIfRequest,
    WhatIfResponse,
)
from app.services import optimization_service, therapist_service
from app.workers.optimization_tasks import run_optimization_task

router = APIRouter()

_ALLOWED_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER, UserRole.THERAPIST)


def _own_therapist_id_if_therapist(db: Session, *, clinic_id: uuid.UUID, current_user: User) -> uuid.UUID | None:
    """Mirrors app.modules.scheduling.router's helper - returns the caller's own therapist_id to
    restrict by, or None for CLINIC_ADMIN/OFFICE_SCHEDULER (no restriction needed)."""
    if current_user.role != UserRole.THERAPIST:
        return None
    therapist = therapist_service.get_therapist_by_user_id(db, clinic_id=clinic_id, user_id=current_user.id)
    if therapist is None:
        raise NotFoundError("Optimization request was not found.", code="OPTIMIZATION_REQUEST_NOT_FOUND")
    return therapist.id


@router.post(
    "/requests",
    response_model=OptimizationRequestPublic,
    status_code=201,
    dependencies=[
        Depends(require_role(*_ALLOWED_ROLES)),
        Depends(
            rate_limit(
                "optimization_create",
                limit=settings.RATE_LIMIT_OPTIMIZATION_MAX,
                window_seconds=settings.RATE_LIMIT_OPTIMIZATION_WINDOW_SECONDS,
            )
        ),
    ],
)
def create_optimization_request(
    payload: CreateOptimizationRequest,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptimizationRequestPublic:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    if restrict_to is not None and payload.therapist_id != restrict_to:
        raise NotFoundError("Therapist was not found.", code="THERAPIST_NOT_FOUND")

    request = optimization_service.create_request(db, clinic_id=clinic_id, requested_by=current_user.id, data=payload)
    run_optimization_task.delay(str(request.id))
    return OptimizationRequestPublic.model_validate(request)


@router.get(
    "/requests/{request_id}",
    response_model=OptimizationRequestPublic,
    dependencies=[Depends(require_role(*_ALLOWED_ROLES))],
)
def get_optimization_request(
    request_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptimizationRequestPublic:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    request = optimization_service.get_request(
        db, clinic_id=clinic_id, request_id=request_id, restrict_to_therapist_id=restrict_to
    )
    return OptimizationRequestPublic.model_validate(request)


@router.get(
    "/requests/{request_id}/recommendations",
    response_model=list[OptimizationRecommendationPublic],
    dependencies=[Depends(require_role(*_ALLOWED_ROLES))],
)
def get_recommendations(
    request_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OptimizationRecommendationPublic]:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    recommendations = optimization_service.list_recommendations(
        db, clinic_id=clinic_id, request_id=request_id, restrict_to_therapist_id=restrict_to
    )
    return [OptimizationRecommendationPublic.model_validate(r) for r in recommendations]


@router.post(
    "/requests/{request_id}/recommendations/{recommendation_id}/accept",
    response_model=AcceptRecommendationResponse,
    dependencies=[Depends(require_role(*_ALLOWED_ROLES))],
)
def accept_recommendation(
    request_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AcceptRecommendationResponse:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    recommendation, appointment_ids = optimization_service.accept_recommendation(
        db,
        clinic_id=clinic_id,
        request_id=request_id,
        recommendation_id=recommendation_id,
        current_user=current_user,
        restrict_to_therapist_id=restrict_to,
    )
    return AcceptRecommendationResponse(
        recommendation=OptimizationRecommendationPublic.model_validate(recommendation), appointment_ids=appointment_ids
    )


@router.post(
    "/requests/{request_id}/recommendations/{recommendation_id}/reject",
    response_model=OptimizationRecommendationPublic,
    dependencies=[Depends(require_role(*_ALLOWED_ROLES))],
)
def reject_recommendation(
    request_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptimizationRecommendationPublic:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    recommendation = optimization_service.reject_recommendation(
        db,
        clinic_id=clinic_id,
        request_id=request_id,
        recommendation_id=recommendation_id,
        restrict_to_therapist_id=restrict_to,
    )
    return OptimizationRecommendationPublic.model_validate(recommendation)


@router.post("/what-if", response_model=WhatIfResponse, dependencies=[Depends(require_role(*_ALLOWED_ROLES))])
def what_if(
    payload: WhatIfRequest,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhatIfResponse:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    return optimization_service.evaluate_what_if(
        db, clinic_id=clinic_id, data=payload, restrict_to_therapist_id=restrict_to
    )


@router.post(
    "/what-if/apply",
    response_model=WhatIfApplyResponse,
    dependencies=[Depends(require_role(UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER, UserRole.THERAPIST))],
)
def apply_what_if(
    payload: WhatIfRequest,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhatIfApplyResponse:
    restrict_to = _own_therapist_id_if_therapist(db, clinic_id=clinic_id, current_user=current_user)
    applied, appointment_id, message = optimization_service.apply_what_if(
        db, clinic_id=clinic_id, created_by=current_user.id, data=payload, restrict_to_therapist_id=restrict_to
    )
    return WhatIfApplyResponse(applied=applied, appointment_id=appointment_id, message=message)
