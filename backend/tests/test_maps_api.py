"""RouteCare AI - /api/v1/maps travel-time and travel-time-matrix endpoint tests."""

import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.permissions import UserRole
from app.services import routing
from app.services.routing import RouteResult
from tests.conftest import auth_headers, make_patient, make_therapist, make_user

MAPS_URL = "/api/v1/maps"


def _install_route(monkeypatch, result: RouteResult | None) -> None:
    class _FakeProvider:
        def route(self, **kwargs):
            return result

        def route_matrix(self, **kwargs):
            return None

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _FakeProvider())


def test_travel_time_between_two_patients(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=40.7, longitude=-74.0)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=40.8, longitude=-74.1)

    _install_route(monkeypatch, RouteResult(distance_meters=13195, duration_seconds=1020))
    response = client.post(
        f"{MAPS_URL}/travel-time",
        json={"origin": {"patient_id": str(patient_a.id)}, "destination": {"patient_id": str(patient_b.id)}},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is True
    assert body["distance_miles"] == 8.2
    assert body["duration_minutes"] == 17.0
    assert body["calculated_at"] is not None


def test_travel_time_between_patient_and_therapist(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic, latitude=40.7, longitude=-74.0)
    therapist = make_therapist(db_session, clinic, home_latitude=40.8, home_longitude=-74.1)

    _install_route(monkeypatch, RouteResult(distance_meters=1609, duration_seconds=300))
    response = client.post(
        f"{MAPS_URL}/travel-time",
        json={"origin": {"therapist_id": str(therapist.id)}, "destination": {"patient_id": str(patient.id)}},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    assert response.json()["reachable"] is True


def test_travel_time_with_raw_coordinates(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    _install_route(monkeypatch, RouteResult(distance_meters=1000, duration_seconds=120))

    response = client.post(
        f"{MAPS_URL}/travel-time",
        json={"origin": {"latitude": 40.0, "longitude": -74.0}, "destination": {"latitude": 40.1, "longitude": -74.1}},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    assert response.json()["reachable"] is True


def test_travel_time_unreachable_returns_200_not_reachable(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=0.0, longitude=0.0)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=89.9, longitude=179.9)

    _install_route(monkeypatch, None)
    response = client.post(
        f"{MAPS_URL}/travel-time",
        json={"origin": {"patient_id": str(patient_a.id)}, "destination": {"patient_id": str(patient_b.id)}},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is False
    assert body["distance_miles"] is None


def test_travel_time_rejects_ungeocoded_patient(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=None, longitude=None)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=40.8, longitude=-74.1)

    response = client.post(
        f"{MAPS_URL}/travel-time",
        json={"origin": {"patient_id": str(patient_a.id)}, "destination": {"patient_id": str(patient_b.id)}},
        headers=auth_headers(admin),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "LOCATION_NOT_GEOCODED"


def test_travel_time_404_for_unknown_patient(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient_b = make_patient(db_session, clinic, latitude=40.8, longitude=-74.1)

    response = client.post(
        f"{MAPS_URL}/travel-time",
        json={"origin": {"patient_id": str(uuid.uuid4())}, "destination": {"patient_id": str(patient_b.id)}},
        headers=auth_headers(admin),
    )

    assert response.status_code == 404


def test_travel_time_cross_clinic_patient_404s(client: TestClient, db_session, clinic) -> None:
    from app.models.clinic import Clinic

    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()
    db_session.refresh(other_clinic)

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    own_patient = make_patient(db_session, clinic, latitude=40.7, longitude=-74.0)
    other_patient = make_patient(db_session, other_clinic, latitude=40.8, longitude=-74.1)

    response = client.post(
        f"{MAPS_URL}/travel-time",
        json={"origin": {"patient_id": str(own_patient.id)}, "destination": {"patient_id": str(other_patient.id)}},
        headers=auth_headers(admin),
    )

    assert response.status_code == 404


def test_travel_time_rejects_ambiguous_location_ref(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic, latitude=40.7, longitude=-74.0)

    response = client.post(
        f"{MAPS_URL}/travel-time",
        json={
            "origin": {"patient_id": str(patient.id), "latitude": 1.0, "longitude": 1.0},
            "destination": {"latitude": 40.1, "longitude": -74.1},
        },
        headers=auth_headers(admin),
    )

    assert response.status_code == 422


def test_travel_time_allowed_for_therapist_role(client: TestClient, db_session, clinic, monkeypatch) -> None:
    therapist_user = make_user(db_session, clinic, role=UserRole.THERAPIST, email="t@example.com")
    _install_route(monkeypatch, RouteResult(distance_meters=1000, duration_seconds=60))

    response = client.post(
        f"{MAPS_URL}/travel-time",
        json={"origin": {"latitude": 40.0, "longitude": -74.0}, "destination": {"latitude": 40.1, "longitude": -74.1}},
        headers=auth_headers(therapist_user),
    )

    assert response.status_code == 200


def test_travel_time_requires_authentication(client: TestClient) -> None:
    response = client.post(
        f"{MAPS_URL}/travel-time",
        json={"origin": {"latitude": 40.0, "longitude": -74.0}, "destination": {"latitude": 40.1, "longitude": -74.1}},
    )
    assert response.status_code == 401


def test_travel_time_matrix_success(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient_a = make_patient(db_session, clinic, first_name="A", latitude=40.7, longitude=-74.0)
    patient_b = make_patient(db_session, clinic, first_name="B", latitude=40.8, longitude=-74.1)
    patient_c = make_patient(db_session, clinic, first_name="C", latitude=40.6, longitude=-74.2)

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

    class _FakeProvider:
        def route(self, **kwargs):
            return None

        def route_matrix(self, **kwargs):
            return raw_matrix

    monkeypatch.setattr(routing, "get_routing_provider", lambda: _FakeProvider())

    response = client.post(
        f"{MAPS_URL}/travel-time-matrix",
        json={"points": [{"patient_id": str(p.id)} for p in (patient_a, patient_b, patient_c)]},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["points"]) == 3
    assert body["matrix"][0][0] is None  # diagonal
    assert body["matrix"][0][1]["reachable"] is True
    assert body["matrix"][0][1]["duration_minutes"] == 10.0


def test_travel_time_matrix_requires_at_least_two_points(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.post(
        f"{MAPS_URL}/travel-time-matrix",
        json={"points": [{"latitude": 1.0, "longitude": 1.0}]},
        headers=auth_headers(admin),
    )
    assert response.status_code == 422


def test_travel_time_matrix_rejects_too_many_points(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    points = [
        {"latitude": float(i % 80), "longitude": float(i % 170)} for i in range(settings.MAPS_MAX_MATRIX_POINTS + 1)
    ]

    response = client.post(f"{MAPS_URL}/travel-time-matrix", json={"points": points}, headers=auth_headers(admin))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MATRIX_TOO_LARGE"
