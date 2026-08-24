"""
RouteCare AI - Maps & travel-time endpoints.

Read-only for every clinic role (CLINIC_ADMIN, OFFICE_SCHEDULER,
THERAPIST) - travel time between two locations isn't sensitive the way
patient CRUD is, and a therapist reasonably wants to check drive time
between their own visits. Every point is still resolved through
patient_service/therapist_service's own clinic-scoped 404 lookups, so a
patient_id/therapist_id from another clinic is unreachable here exactly
like everywhere else in the API.

This module intentionally has no create/update/delete endpoints -
geocoding patients/therapists stays on their own routers
(POST /patients/{id}/geocode, POST /therapists/{id}/geocode) since it
mutates those resources; this module only ever computes travel time
between locations that already have coordinates.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_clinic_id
from app.core.exceptions import BusinessRuleError, ValidationError
from app.core.permissions import UserRole, require_role
from app.database.session import get_db
from app.schemas.maps import (
    LocationRef,
    MatrixCell,
    ResolvedPoint,
    TravelTimeMatrixRequest,
    TravelTimeMatrixResponse,
    TravelTimeRequest,
    TravelTimeResponse,
)
from app.services import patient_service, therapist_service
from app.services.travel_time_service import LocationPoint, MatrixTooLargeError, get_travel_time, get_travel_time_matrix

router = APIRouter()

_READ_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER, UserRole.THERAPIST)


def _resolve_point(db: Session, *, clinic_id: uuid.UUID, ref: LocationRef) -> tuple[LocationPoint, ResolvedPoint]:
    if ref.patient_id is not None:
        patient = patient_service.get_patient(db, clinic_id=clinic_id, patient_id=ref.patient_id)
        if patient.latitude is None or patient.longitude is None:
            raise BusinessRuleError(f"{patient.full_name} has not been geocoded yet.", code="LOCATION_NOT_GEOCODED")
        latitude, longitude = float(patient.latitude), float(patient.longitude)
        return (
            LocationPoint(latitude=latitude, longitude=longitude),
            ResolvedPoint(
                type="patient", id=patient.id, label=patient.full_name, latitude=latitude, longitude=longitude
            ),
        )

    if ref.therapist_id is not None:
        therapist = therapist_service.get_therapist(db, clinic_id=clinic_id, therapist_id=ref.therapist_id)
        if therapist.home_latitude is None or therapist.home_longitude is None:
            raise BusinessRuleError(
                f"{therapist.first_name} {therapist.last_name} has not been geocoded yet.", code="LOCATION_NOT_GEOCODED"
            )
        latitude, longitude = float(therapist.home_latitude), float(therapist.home_longitude)
        label = f"{therapist.first_name} {therapist.last_name}"
        return (
            LocationPoint(latitude=latitude, longitude=longitude),
            ResolvedPoint(type="therapist", id=therapist.id, label=label, latitude=latitude, longitude=longitude),
        )

    # LocationRef's validator guarantees latitude/longitude are set together when neither id is.
    assert ref.latitude is not None and ref.longitude is not None
    return (
        LocationPoint(latitude=ref.latitude, longitude=ref.longitude),
        ResolvedPoint(
            type="coordinates", id=None, label="Custom location", latitude=ref.latitude, longitude=ref.longitude
        ),
    )


@router.post("/travel-time", response_model=TravelTimeResponse, dependencies=[Depends(require_role(*_READ_ROLES))])
def calculate_travel_time(
    payload: TravelTimeRequest,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> TravelTimeResponse:
    origin_point, _ = _resolve_point(db, clinic_id=clinic_id, ref=payload.origin)
    destination_point, _ = _resolve_point(db, clinic_id=clinic_id, ref=payload.destination)

    result = get_travel_time(clinic_id=clinic_id, origin=origin_point, destination=destination_point)
    if result is None:
        return TravelTimeResponse(
            reachable=False, distance_miles=None, duration_minutes=None, calculated_at=None, cached=False
        )
    return TravelTimeResponse(
        reachable=True,
        distance_miles=result.distance_miles,
        duration_minutes=result.duration_minutes,
        calculated_at=result.calculated_at,
        cached=result.cached,
    )


@router.post(
    "/travel-time-matrix", response_model=TravelTimeMatrixResponse, dependencies=[Depends(require_role(*_READ_ROLES))]
)
def calculate_travel_time_matrix(
    payload: TravelTimeMatrixRequest,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> TravelTimeMatrixResponse:
    resolved = [_resolve_point(db, clinic_id=clinic_id, ref=ref) for ref in payload.points]
    points = [p for p, _ in resolved]
    labels = [r for _, r in resolved]

    try:
        matrix = get_travel_time_matrix(clinic_id=clinic_id, points=points)
    except MatrixTooLargeError as exc:
        raise ValidationError(str(exc), code="MATRIX_TOO_LARGE") from exc
    except ValueError as exc:
        raise ValidationError(str(exc), code="INVALID_MATRIX_REQUEST") from exc

    cells: list[list[MatrixCell | None]] = []
    for i, row in enumerate(matrix):
        cell_row: list[MatrixCell | None] = []
        for j, cell in enumerate(row):
            if i == j:
                cell_row.append(None)
            elif cell is None:
                cell_row.append(MatrixCell(reachable=False, distance_miles=None, duration_minutes=None, cached=False))
            else:
                cell_row.append(
                    MatrixCell(
                        reachable=True,
                        distance_miles=cell.distance_miles,
                        duration_minutes=cell.duration_minutes,
                        cached=cell.cached,
                    )
                )
        cells.append(cell_row)

    return TravelTimeMatrixResponse(points=labels, matrix=cells, calculated_at=datetime.now(timezone.utc))
