"""
RouteCare AI - Patient geocoding lifecycle tests (Phase 5).

The autouse `_no_external_geocoding_or_routing` fixture (conftest.py)
already makes every patient created in the existing test suite resolve
to a FAILED geocode by default (matching pre-Phase-5 NullGeocodingProvider
behavior) - tests here override `geocoding.get_geocoding_provider` per
case to exercise success, manual overrides, and re-geocode logic.
"""

import uuid

from fastapi.testclient import TestClient

from app.core.permissions import UserRole
from app.models.patient import GeocodingStatus
from app.services import geocoding
from tests.conftest import auth_headers, make_patient, make_user

PATIENTS_URL = "/api/v1/patients"

VALID_PAYLOAD = {
    "first_name": "Mary",
    "last_name": "Smith",
    "address_line_1": "123 Main St",
    "city": "Hoboken",
    "state": "NJ",
    "zip_code": "07030",
}


class _SuccessProvider:
    def __init__(
        self, lat: float = 40.7, lng: float = -74.0, normalized: str = "123 Main St, Hoboken, NJ, USA"
    ) -> None:
        self.lat, self.lng, self.normalized = lat, lng, normalized

    def geocode(self, **kwargs):
        return geocoding.GeocodeResult(latitude=self.lat, longitude=self.lng, normalized_address=self.normalized)


def test_create_patient_without_coordinates_geocodes_automatically(
    client: TestClient, db_session, clinic, monkeypatch
) -> None:
    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _SuccessProvider())
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    response = client.post(PATIENTS_URL, json=VALID_PAYLOAD, headers=auth_headers(admin))

    assert response.status_code == 201
    body = response.json()
    assert body["geocoding_status"] == "GEOCODED"
    assert body["latitude"] == 40.7
    assert body["longitude"] == -74.0
    assert body["location_verified"] is False
    assert body["geocoded_at"] is not None


def test_create_patient_geocoding_failure_still_creates_patient(client: TestClient, db_session, clinic) -> None:
    # No override - the autouse fake always returns None, i.e. "address could not be geocoded".
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    response = client.post(PATIENTS_URL, json=VALID_PAYLOAD, headers=auth_headers(admin))

    assert response.status_code == 201  # geocoding failure never blocks patient creation
    body = response.json()
    assert body["geocoding_status"] == "FAILED"
    assert body["latitude"] is None
    assert body["location_verified"] is False


def test_create_patient_with_explicit_coordinates_is_manual(
    client: TestClient, db_session, clinic, monkeypatch
) -> None:
    calls = []
    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: calls.append(1) or _SuccessProvider())
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)

    payload = {**VALID_PAYLOAD, "latitude": 41.0, "longitude": -75.0}
    response = client.post(PATIENTS_URL, json=payload, headers=auth_headers(admin))

    assert response.status_code == 201
    body = response.json()
    assert body["geocoding_status"] == "MANUAL"
    assert body["location_verified"] is True
    assert body["latitude"] == 41.0
    assert not calls  # explicit coordinates never call the provider


def test_update_address_regeocodes_when_not_verified(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(
        db_session,
        clinic,
        latitude=40.0,
        longitude=-74.0,
        geocoding_status=GeocodingStatus.GEOCODED,
        location_verified=False,
    )

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _SuccessProvider(lat=41.5, lng=-73.5))
    response = client.patch(
        f"{PATIENTS_URL}/{patient.id}", json={"address_line_1": "456 Other Ave"}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["latitude"] == 41.5
    assert body["longitude"] == -73.5
    assert body["geocoding_status"] == "GEOCODED"


def test_update_address_skips_regeocode_when_verified(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(
        db_session,
        clinic,
        latitude=40.0,
        longitude=-74.0,
        geocoding_status=GeocodingStatus.MANUAL,
        location_verified=True,
    )

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _SuccessProvider(lat=99.0, lng=99.0))
    response = client.patch(
        f"{PATIENTS_URL}/{patient.id}", json={"address_line_1": "456 Other Ave"}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["latitude"] == 40.0  # untouched - verified coordinates are never silently overwritten
    assert body["longitude"] == -74.0
    assert body["geocoding_status"] == "MANUAL"


def test_update_can_unmark_verified_to_allow_regeocode_on_same_request(
    client: TestClient, db_session, clinic, monkeypatch
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(
        db_session,
        clinic,
        latitude=40.0,
        longitude=-74.0,
        geocoding_status=GeocodingStatus.MANUAL,
        location_verified=True,
    )

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _SuccessProvider(lat=41.5, lng=-73.5))
    response = client.patch(
        f"{PATIENTS_URL}/{patient.id}",
        json={"address_line_1": "456 Other Ave", "location_verified": False},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["latitude"] == 41.5
    assert body["geocoding_status"] == "GEOCODED"
    assert body["location_verified"] is False


def test_update_explicit_coordinates_marks_manual_and_verified(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic, geocoding_status=GeocodingStatus.FAILED)

    response = client.patch(
        f"{PATIENTS_URL}/{patient.id}", json={"latitude": 42.0, "longitude": -71.0}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["geocoding_status"] == "MANUAL"
    assert body["location_verified"] is True


def test_update_can_flip_verified_without_changing_coordinates(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(
        db_session,
        clinic,
        latitude=40.0,
        longitude=-74.0,
        geocoding_status=GeocodingStatus.GEOCODED,
        location_verified=False,
    )

    response = client.patch(
        f"{PATIENTS_URL}/{patient.id}", json={"location_verified": True}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["location_verified"] is True
    assert body["latitude"] == 40.0


def test_address_change_that_fails_to_regeocode_clears_stale_coordinates(
    client: TestClient, db_session, clinic
) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(
        db_session,
        clinic,
        latitude=40.0,
        longitude=-74.0,
        geocoding_status=GeocodingStatus.GEOCODED,
        location_verified=False,
    )

    # No override - autouse fake fails, simulating an address edit to somewhere ungeocodable.
    response = client.patch(
        f"{PATIENTS_URL}/{patient.id}", json={"address_line_1": "Bad Address"}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["latitude"] is None
    assert body["geocoding_status"] == "FAILED"


def test_geocode_patient_endpoint_success(client: TestClient, db_session, clinic, monkeypatch) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic, geocoding_status=GeocodingStatus.PENDING)

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _SuccessProvider())
    response = client.post(f"{PATIENTS_URL}/{patient.id}/geocode", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["normalized_address"] == "123 Main St, Hoboken, NJ, USA"
    assert body["patient"]["geocoding_status"] == "GEOCODED"


def test_geocode_patient_endpoint_failure(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    patient = make_patient(db_session, clinic, geocoding_status=GeocodingStatus.PENDING)

    response = client.post(f"{PATIENTS_URL}/{patient.id}/geocode", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["normalized_address"] is None
    assert body["patient"]["geocoding_status"] == "FAILED"


def test_geocode_patient_endpoint_404_for_unknown_patient(client: TestClient, db_session, clinic) -> None:
    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    response = client.post(f"{PATIENTS_URL}/{uuid.uuid4()}/geocode", headers=auth_headers(admin))
    assert response.status_code == 404


def test_geocode_patient_endpoint_cross_clinic_404s(client: TestClient, db_session, clinic) -> None:
    from app.models.clinic import Clinic

    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()
    db_session.refresh(other_clinic)

    admin = make_user(db_session, clinic, role=UserRole.CLINIC_ADMIN)
    other_patient = make_patient(db_session, other_clinic)

    response = client.post(f"{PATIENTS_URL}/{other_patient.id}/geocode", headers=auth_headers(admin))
    assert response.status_code == 404


def test_geocode_patient_endpoint_forbidden_for_therapist(client: TestClient, db_session, clinic) -> None:
    therapist_user = make_user(db_session, clinic, role=UserRole.THERAPIST, email="t@example.com")
    patient = make_patient(db_session, clinic)

    response = client.post(f"{PATIENTS_URL}/{patient.id}/geocode", headers=auth_headers(therapist_user))
    assert response.status_code == 403


def test_geocode_patient_endpoint_allowed_for_office_scheduler(
    client: TestClient, db_session, clinic, monkeypatch
) -> None:
    scheduler = make_user(db_session, clinic, role=UserRole.OFFICE_SCHEDULER, email="s@example.com")
    patient = make_patient(db_session, clinic)

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _SuccessProvider())
    response = client.post(f"{PATIENTS_URL}/{patient.id}/geocode", headers=auth_headers(scheduler))
    assert response.status_code == 200
