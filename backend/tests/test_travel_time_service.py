"""
RouteCare AI - Travel-time service tests.

Exercises app.services.travel_time_service against a fake routing
provider (monkeypatched onto app.services.routing.get_routing_provider)
plus the autouse in-memory fake Redis from conftest - no network, no
real cache required.
"""

import pytest

from app.core.config import settings
from app.services import routing, travel_time_service
from app.services.routing import RouteResult
from app.services.travel_time_service import LocationPoint, MatrixTooLargeError


def _install_fake_routing(
    monkeypatch: pytest.MonkeyPatch, *, route_calls: list, matrix_calls: list, route_result=None, matrix_result=None
):
    class _FakeProvider:
        def route(self, **kwargs):
            route_calls.append(kwargs)
            return route_result

        def route_matrix(self, **kwargs):
            matrix_calls.append(kwargs)
            return matrix_result

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _FakeProvider())


def test_get_travel_time_success_and_cache_hit(monkeypatch: pytest.MonkeyPatch, clinic) -> None:
    calls: list = []
    _install_fake_routing(
        monkeypatch,
        route_calls=calls,
        matrix_calls=[],
        route_result=RouteResult(distance_meters=8047, duration_seconds=1020),
    )

    origin = LocationPoint(latitude=40.7128, longitude=-74.0060)
    destination = LocationPoint(latitude=40.6892, longitude=-74.0445)

    first = travel_time_service.get_travel_time(clinic_id=clinic.id, origin=origin, destination=destination)
    second = travel_time_service.get_travel_time(clinic_id=clinic.id, origin=origin, destination=destination)

    assert first is not None
    assert first.distance_miles == pytest.approx(5.0, abs=0.05)
    assert first.duration_minutes == pytest.approx(17.0, abs=0.1)
    assert first.cached is False

    assert second is not None
    assert second.cached is True
    assert second.distance_miles == first.distance_miles
    assert len(calls) == 1  # second call was served from cache, no second provider call


def test_get_travel_time_unreachable_returns_none(monkeypatch: pytest.MonkeyPatch, clinic) -> None:
    _install_fake_routing(monkeypatch, route_calls=[], matrix_calls=[], route_result=None)

    result = travel_time_service.get_travel_time(
        clinic_id=clinic.id,
        origin=LocationPoint(latitude=0.0, longitude=0.0),
        destination=LocationPoint(latitude=89.9, longitude=179.9),
    )

    assert result is None


def test_get_travel_time_has_timestamp(monkeypatch: pytest.MonkeyPatch, clinic) -> None:
    _install_fake_routing(
        monkeypatch,
        route_calls=[],
        matrix_calls=[],
        route_result=RouteResult(distance_meters=1000, duration_seconds=120),
    )

    result = travel_time_service.get_travel_time(
        clinic_id=clinic.id,
        origin=LocationPoint(latitude=1.0, longitude=1.0),
        destination=LocationPoint(latitude=2.0, longitude=2.0),
    )

    assert result is not None
    assert result.calculated_at is not None


def test_get_travel_time_matrix_uses_one_batched_call(monkeypatch: pytest.MonkeyPatch, clinic) -> None:
    matrix_calls: list = []
    raw_matrix = [
        [
            None,
            RouteResult(distance_meters=5000, duration_seconds=600),
            RouteResult(distance_meters=8000, duration_seconds=900),
        ],
        [
            RouteResult(distance_meters=5000, duration_seconds=600),
            None,
            RouteResult(distance_meters=4000, duration_seconds=450),
        ],
        [
            RouteResult(distance_meters=8000, duration_seconds=900),
            RouteResult(distance_meters=4000, duration_seconds=450),
            None,
        ],
    ]
    _install_fake_routing(monkeypatch, route_calls=[], matrix_calls=matrix_calls, matrix_result=raw_matrix)

    points = [
        LocationPoint(latitude=40.7, longitude=-74.0),
        LocationPoint(latitude=40.8, longitude=-74.1),
        LocationPoint(latitude=40.6, longitude=-74.2),
    ]
    matrix = travel_time_service.get_travel_time_matrix(clinic_id=clinic.id, points=points)

    assert len(matrix_calls) == 1  # one matrix call for all 3x3 pairs, not 6 pairwise calls
    assert matrix[0][1] is not None
    assert matrix[0][1].duration_minutes == pytest.approx(10.0, abs=0.1)
    assert matrix[1][2].distance_miles == pytest.approx(2.49, abs=0.05)


def test_get_travel_time_matrix_fully_cached_skips_provider(monkeypatch: pytest.MonkeyPatch, clinic) -> None:
    matrix_calls: list = []
    raw_matrix = [
        [None, RouteResult(distance_meters=1000, duration_seconds=60)],
        [RouteResult(distance_meters=1000, duration_seconds=60), None],
    ]
    _install_fake_routing(monkeypatch, route_calls=[], matrix_calls=matrix_calls, matrix_result=raw_matrix)

    points = [LocationPoint(latitude=10.0, longitude=10.0), LocationPoint(latitude=11.0, longitude=11.0)]
    travel_time_service.get_travel_time_matrix(clinic_id=clinic.id, points=points)
    assert len(matrix_calls) == 1

    travel_time_service.get_travel_time_matrix(clinic_id=clinic.id, points=points)
    assert len(matrix_calls) == 1  # second call fully served from cache


def test_get_travel_time_matrix_unreachable_pair_stays_none(monkeypatch: pytest.MonkeyPatch, clinic) -> None:
    raw_matrix = [[None, None], [None, None]]
    _install_fake_routing(monkeypatch, route_calls=[], matrix_calls=[], matrix_result=raw_matrix)

    points = [LocationPoint(latitude=10.0, longitude=10.0), LocationPoint(latitude=89.9, longitude=179.9)]
    matrix = travel_time_service.get_travel_time_matrix(clinic_id=clinic.id, points=points)

    assert matrix[0][1] is None
    assert matrix[1][0] is None


def test_get_travel_time_matrix_whole_request_failure_does_not_poison_cache(
    monkeypatch: pytest.MonkeyPatch, clinic
) -> None:
    _install_fake_routing(monkeypatch, route_calls=[], matrix_calls=[], matrix_result=None)

    points = [LocationPoint(latitude=10.0, longitude=10.0), LocationPoint(latitude=11.0, longitude=11.0)]
    matrix = travel_time_service.get_travel_time_matrix(clinic_id=clinic.id, points=points)
    assert matrix[0][1] is None

    # A working provider on the next attempt should be able to fill it in - proves nothing was
    # cached as a false "unreachable" during the earlier failure.
    good_matrix = [
        [None, RouteResult(distance_meters=1000, duration_seconds=60)],
        [RouteResult(distance_meters=1000, duration_seconds=60), None],
    ]
    _install_fake_routing(monkeypatch, route_calls=[], matrix_calls=[], matrix_result=good_matrix)
    retried = travel_time_service.get_travel_time_matrix(clinic_id=clinic.id, points=points)
    assert retried[0][1] is not None


def test_get_travel_time_matrix_rejects_single_point(clinic) -> None:
    with pytest.raises(ValueError):
        travel_time_service.get_travel_time_matrix(
            clinic_id=clinic.id, points=[LocationPoint(latitude=1.0, longitude=1.0)]
        )


def test_get_travel_time_matrix_rejects_too_many_points(clinic) -> None:
    points = [LocationPoint(latitude=float(i), longitude=float(i)) for i in range(settings.MAPS_MAX_MATRIX_POINTS + 1)]
    with pytest.raises(MatrixTooLargeError):
        travel_time_service.get_travel_time_matrix(clinic_id=clinic.id, points=points)


def test_travel_time_cache_is_scoped_per_clinic(monkeypatch: pytest.MonkeyPatch, clinic, db_session) -> None:
    from app.models.clinic import Clinic

    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()
    db_session.refresh(other_clinic)

    calls: list = []
    _install_fake_routing(
        monkeypatch,
        route_calls=calls,
        matrix_calls=[],
        route_result=RouteResult(distance_meters=1000, duration_seconds=60),
    )

    origin = LocationPoint(latitude=10.0, longitude=10.0)
    destination = LocationPoint(latitude=11.0, longitude=11.0)

    travel_time_service.get_travel_time(clinic_id=clinic.id, origin=origin, destination=destination)
    travel_time_service.get_travel_time(clinic_id=other_clinic.id, origin=origin, destination=destination)

    assert len(calls) == 2  # not shared across clinics
