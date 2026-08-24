"""RouteCare AI - Therapist home-address geocoding lifecycle tests (Phase 5). Mirrors
tests/test_patients_geocoding.py - see that file's module docstring for the autouse-fake context."""

import uuid

from fastapi.testclient import TestClient

from app.core.permissions import UserRole
from app.models.patient import GeocodingStatus
from app.services import geocoding
from tests.conftest import auth_headers, make_therapist, make_user

THERAPISTS_URL = "/api/v1/therapists"


class _SuccessProvider:
    def __init__(
        self, lat: float = 40.7, lng: float = -74.0, normalized: str = "1 Clinic Way, Newark, NJ, USA"
    ) -> None:
        self.lat, self.lng, self.normalized = lat, lng, normalized

    def geocode(self, **kwargs):
        return geocoding.GeocodeResult(latitude=self.lat, longitude=self.lng, normalized_address=self.normalized)


def test_create_therapist_with_home_address_geocodes_automatically(
    client: TestClient, db_session, clinic, monkeypatch
) -> None:
    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _SuccessProvider())
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    payload = {
        "first_name": "Terry",
        "last_name": "Therapist",
        "email": "terry@example.com",
        "password": "Str0ng!Passw0rd",
        "home_address": "1 Clinic Way, Newark, NJ",
    }
    response = client.post(THERAPISTS_URL, json=payload, headers=auth_headers(admin))

    assert response.status_code == 201
    body = response.json()
    assert body["geocoding_status"] == "GEOCODED"
    assert body["home_latitude"] == 40.7


def test_create_therapist_without_home_address_stays_pending(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    payload = {
        "first_name": "Terry",
        "last_name": "Therapist",
        "email": "terry2@example.com",
        "password": "Str0ng!Passw0rd",
    }
    response = client.post(THERAPISTS_URL, json=payload, headers=auth_headers(admin))

    assert response.status_code == 201
    body = response.json()
    assert body["geocoding_status"] == "PENDING"


def test_create_therapist_with_explicit_coordinates_is_manual(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    payload = {
        "first_name": "Terry",
        "last_name": "Therapist",
        "email": "terry3@example.com",
        "password": "Str0ng!Passw0rd",
        "home_address": "1 Clinic Way, Newark, NJ",
        "home_latitude": 40.1,
        "home_longitude": -74.5,
    }
    response = client.post(THERAPISTS_URL, json=payload, headers=auth_headers(admin))

    assert response.status_code == 201
    body = response.json()
    assert body["geocoding_status"] == "MANUAL"
    assert body["location_verified"] is True


def test_update_home_address_skips_regeocode_when_verified(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(
        db_session,
        clinic,
        home_latitude=40.0,
        home_longitude=-74.0,
        geocoding_status=GeocodingStatus.MANUAL,
        location_verified=True,
    )

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _SuccessProvider(lat=99.0, lng=99.0))
    response = client.patch(
        f"{THERAPISTS_URL}/{therapist.id}", json={"home_address": "New Address"}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["home_latitude"] == 40.0


def test_update_home_address_regeocodes_when_not_verified(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(
        db_session,
        clinic,
        home_latitude=40.0,
        home_longitude=-74.0,
        geocoding_status=GeocodingStatus.GEOCODED,
        location_verified=False,
    )

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _SuccessProvider(lat=41.0, lng=-73.0))
    response = client.patch(
        f"{THERAPISTS_URL}/{therapist.id}", json={"home_address": "New Address"}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["home_latitude"] == 41.0
    assert body["geocoding_status"] == "GEOCODED"


def test_geocode_therapist_endpoint_success(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(
        db_session, clinic, home_address="1 Clinic Way, Newark, NJ", geocoding_status=GeocodingStatus.PENDING
    )

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _SuccessProvider())
    response = client.post(f"{THERAPISTS_URL}/{therapist.id}/geocode", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["therapist"]["geocoding_status"] == "GEOCODED"


def test_geocode_therapist_endpoint_no_address_returns_business_error(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    therapist = make_therapist(db_session, clinic, home_address=None)

    response = client.post(f"{THERAPISTS_URL}/{therapist.id}/geocode", headers=auth_headers(admin))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_ADDRESS_TO_GEOCODE"


def test_geocode_therapist_endpoint_404_for_unknown_therapist(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.post(f"{THERAPISTS_URL}/{uuid.uuid4()}/geocode", headers=auth_headers(admin))
    assert response.status_code == 404


def test_geocode_therapist_endpoint_forbidden_for_therapist_role(client: TestClient, db_session, clinic) -> None:
    therapist = make_therapist(db_session, clinic, home_address="1 Clinic Way, Newark, NJ")
    therapist_user = make_user(db_session, clinic, role=UserRole.THERAPIST, email="other@example.com")

    response = client.post(f"{THERAPISTS_URL}/{therapist.id}/geocode", headers=auth_headers(therapist_user))
    assert response.status_code == 403
