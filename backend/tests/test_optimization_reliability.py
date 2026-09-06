"""Tests for Phase 9 optimization-job reliability: a redelivered/duplicate Celery message for a
request that's already PROCESSING or COMPLETED must never recompute and insert a second set of
recommendation rows."""

from datetime import date, time

import pytest
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.optimization import OptimizationRecommendation, OptimizationRequest, OptimizationStatus
from app.services import optimization_service
from app.services.routing import RouteResult
from tests.conftest import make_appointment, make_patient, make_therapist, make_user, make_weekday_availability

MONDAY = date(2026, 8, 24)
assert MONDAY.weekday() == 0


class _DeterministicFakeRouting:
    def route(self, *, origin_lat, origin_lng, dest_lat, dest_lng):
        seconds = (abs(origin_lat - dest_lat) + abs(origin_lng - dest_lng)) * 100_000
        return RouteResult(distance_meters=seconds * 10, duration_seconds=seconds)

    def route_matrix(self, *, points):
        size = len(points)
        return [
            [
                None
                if i == j
                else self.route(origin_lat=points[i][0], origin_lng=points[i][1], dest_lat=points[j][0], dest_lng=points[j][1])
                for j in range(size)
            ]
            for i in range(size)
        ]


@pytest.fixture(autouse=True)
def _deterministic_routing(monkeypatch: pytest.MonkeyPatch):
    from app.services import routing

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _DeterministicFakeRouting())


def _setup(db_session: Session, clinic):
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_latitude=40.0, home_longitude=-74.0)
    make_weekday_availability(db_session, therapist)
    patient = make_patient(db_session, clinic, latitude=40.001, longitude=-74.0)
    make_appointment(
        db_session, clinic, patient=patient, therapist=therapist, created_by=admin.id,
        scheduled_date=MONDAY, start_time=time(9, 0),
    )
    return admin, therapist


def test_redelivered_completed_request_is_not_recomputed(db_session: Session, clinic) -> None:
    admin, therapist = _setup(db_session, clinic)

    from app.schemas.optimization import CreateOptimizationRequest

    request = optimization_service.create_request(
        db_session,
        clinic_id=clinic.id,
        requested_by=admin.id,
        data=CreateOptimizationRequest(mode="DAY_SCHEDULE_OPTIMIZATION", therapist_id=therapist.id, target_date=MONDAY),
    )

    optimization_service.run_optimization(db_session, request.id)
    db_session.refresh(request)
    assert request.status == OptimizationStatus.COMPLETED
    first_run_count = (
        db_session.query(OptimizationRecommendation)
        .filter(OptimizationRecommendation.optimization_request_id == request.id)
        .count()
    )
    assert first_run_count > 0

    # Simulate a redelivered/duplicate Celery message for the same (already-completed) request.
    optimization_service.run_optimization(db_session, request.id)

    second_run_count = (
        db_session.query(OptimizationRecommendation)
        .filter(OptimizationRecommendation.optimization_request_id == request.id)
        .count()
    )
    assert second_run_count == first_run_count  # no duplicate rows inserted


def test_redelivered_processing_request_is_not_recomputed(db_session: Session, clinic) -> None:
    admin, therapist = _setup(db_session, clinic)

    from app.schemas.optimization import CreateOptimizationRequest

    request = optimization_service.create_request(
        db_session,
        clinic_id=clinic.id,
        requested_by=admin.id,
        data=CreateOptimizationRequest(mode="DAY_SCHEDULE_OPTIMIZATION", therapist_id=therapist.id, target_date=MONDAY),
    )

    # Simulate a worker crashing right after marking PROCESSING but before finishing.
    request.status = OptimizationStatus.PROCESSING
    db_session.commit()

    optimization_service.run_optimization(db_session, request.id)

    db_session.refresh(request)
    assert request.status == OptimizationStatus.PROCESSING  # left exactly as the (only legitimate) run should find it
    assert (
        db_session.query(OptimizationRecommendation)
        .filter(OptimizationRecommendation.optimization_request_id == request.id)
        .count()
        == 0
    )
