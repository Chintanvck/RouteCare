"""
RouteCare AI - Shared test fixtures.

Tests run against an in-memory SQLite database (via app.database.types.GUID's
portable column type) rather than requiring a local Postgres instance.
"""

import uuid
from collections.abc import Generator
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers models with Base.metadata
from app.core.config import settings
from app.core.permissions import UserRole
from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.appointment import Appointment, AppointmentSource, AppointmentStatus
from app.models.clinic import Clinic
from app.models.patient import Patient
from app.models.therapist import Therapist
from app.models.therapist_availability import TherapistAvailability
from app.models.user import User

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _import_storage_tmp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets its own throwaway import-file storage directory, never the real var/imports."""
    monkeypatch.setattr(settings, "IMPORT_STORAGE_DIR", str(tmp_path / "imports"))


class _FakeGeocodingProvider:
    """Deterministic stand-in for the real Nominatim provider - always "fails" (returns None),
    matching pre-Phase-5 behavior (NullGeocodingProvider) so every existing test that creates a
    patient/therapist without explicit coordinates keeps working unchanged. Tests that need to
    exercise a successful/specific geocode result monkeypatch
    `app.services.geocoding.get_geocoding_provider` again with their own fake."""

    def geocode(self, *, address_line_1: str, city: str, state: str, zip_code: str):
        return None


class _FakeRoutingProvider:
    """Deterministic stand-in for the real OSRM provider - always reports "no route" so no test
    accidentally depends on network access. Tests exercising routing/travel-time success paths
    monkeypatch `app.services.routing.get_routing_provider` with their own fake."""

    def route(self, *, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float):
        return None

    def route_matrix(self, *, points: list[tuple[float, float]]):
        return None


@pytest.fixture(autouse=True)
def _no_external_geocoding_or_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test suite must never depend on real Nominatim/OSRM network access. Every test gets
    these fakes by default; override per-test with monkeypatch.setattr on the same two targets to
    exercise specific success/failure/timeout scenarios."""
    from app.services import geocoding, routing

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _FakeGeocodingProvider())
    monkeypatch.setattr(routing, "get_routing_provider", lambda: _FakeRoutingProvider())


@pytest.fixture(autouse=True)
def _fake_redis_cache(monkeypatch: pytest.MonkeyPatch) -> dict:
    """In-memory stand-in for Redis so cache tests are deterministic and no test requires a real
    Redis instance - app.core.cache already treats any Redis error as a miss, but that would make
    every cache test silently a no-op rather than actually exercising caching."""
    from app.core import cache as cache_module

    store: dict[str, str] = {}

    def fake_get(key: str) -> str | None:
        return store.get(key)

    def fake_setex(key: str, ttl_seconds: int, value: str) -> None:
        store[key] = value

    class _FakeRedisClient:
        get = staticmethod(fake_get)
        setex = staticmethod(fake_setex)

    monkeypatch.setattr(cache_module, "get_redis_client", lambda: _FakeRedisClient())
    return store


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


VALID_PASSWORD = "Str0ng!Passw0rd"


@pytest.fixture()
def clinic(db_session: Session) -> Clinic:
    c = Clinic(name="Test Clinic")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture()
def make_admin(db_session: Session, clinic: Clinic) -> User:
    """A CLINIC_ADMIN in `clinic` - convenience for tests (e.g. imports) that mostly just need
    *some* authorized uploader/actor and don't care about exercising other roles."""
    return make_user(db_session, clinic, email="admin@example.com", role=UserRole.CLINIC_ADMIN)


def make_user(
    db_session: Session,
    clinic: Clinic | None,
    *,
    email: str = "user@example.com",
    role: UserRole = UserRole.CLINIC_ADMIN,
    password: str = VALID_PASSWORD,
    is_active: bool = True,
) -> User:
    user = User(
        clinic_id=clinic.id if clinic else None,
        first_name="Test",
        last_name="User",
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth_headers(user: User) -> dict[str, str]:
    """Mint a valid access token directly, bypassing a real login round-trip - mirrors the token
    payload auth_service._issue_token_pair builds."""
    token = create_access_token(
        {
            "sub": str(user.id),
            "user_id": str(user.id),
            "clinic_id": str(user.clinic_id) if user.clinic_id else None,
            "role": user.role.value,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def make_patient(
    db_session: Session,
    clinic: Clinic,
    *,
    first_name: str = "Mary",
    last_name: str = "Smith",
    zip_code: str = "07030",
    **overrides,
) -> Patient:
    defaults = dict(
        clinic_id=clinic.id,
        first_name=first_name,
        last_name=last_name,
        address_line_1="123 Main St",
        city="Hoboken",
        state="NJ",
        zip_code=zip_code,
    )
    defaults.update(overrides)
    patient = Patient(**defaults)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    return patient


def build_xlsx_bytes(headers: list[str], rows: list[list]) -> bytes:
    """Build a realistic-shaped .xlsx workbook in memory - no binary fixture files to maintain in the repo."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


THERAOFFICE_HEADERS = [
    "Patient Full Name",
    "Phone",
    "Email",
    "Address",
    "City",
    "State",
    "ZIP",
]


def build_theraoffice_xlsx(rows: list[list]) -> bytes:
    """Rows shaped like [full_name, phone, email, address, city, state, zip]."""
    return build_xlsx_bytes(THERAOFFICE_HEADERS, rows)


@pytest.fixture()
def sync_import_tasks(monkeypatch: pytest.MonkeyPatch, db_session: Session):
    """Redirects the Celery task .delay() calls the import router makes to run the same
    service-layer logic synchronously against the test's SQLite session - the tasks' real
    SessionLocal() is bound to the configured DATABASE_URL (Postgres), not this test DB."""
    from app.services import import_service
    from app.workers.import_tasks import execute_import_task, validate_import_task

    def fake_validate_delay(import_id: str) -> None:
        import_service.run_row_validation(db_session, uuid.UUID(import_id))

    def fake_execute_delay(import_id: str, include_duplicates: bool) -> None:
        import_service.run_import_execution(db_session, uuid.UUID(import_id), include_duplicates=include_duplicates)

    monkeypatch.setattr(validate_import_task, "delay", fake_validate_delay)
    monkeypatch.setattr(execute_import_task, "delay", fake_execute_delay)


def make_therapist(
    db_session: Session,
    clinic: Clinic,
    *,
    email: str = "therapist@example.com",
    first_name: str = "Terry",
    last_name: str = "Therapist",
    is_active: bool = True,
    password: str = VALID_PASSWORD,
    **overrides,
) -> Therapist:
    user = User(
        clinic_id=clinic.id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=hash_password(password),
        role=UserRole.THERAPIST,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.flush()

    defaults = dict(clinic_id=clinic.id, user_id=user.id)
    defaults.update(overrides)
    therapist = Therapist(**defaults)
    db_session.add(therapist)
    db_session.commit()
    db_session.refresh(therapist)
    return therapist


def make_therapist_availability(
    db_session: Session,
    therapist: Therapist,
    *,
    day_of_week: int,
    start_time: time = time(9, 0),
    end_time: time = time(17, 0),
    is_available: bool = True,
) -> TherapistAvailability:
    row = TherapistAvailability(
        therapist_id=therapist.id,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        is_available=is_available,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def make_weekday_availability(db_session: Session, therapist: Therapist, **kwargs) -> None:
    """Monday-Friday (0-4), 9am-5pm by default - the common case most appointment tests want."""
    for day in range(5):
        make_therapist_availability(db_session, therapist, day_of_week=day, **kwargs)


def make_appointment(
    db_session: Session,
    clinic: Clinic,
    *,
    patient: Patient,
    therapist: Therapist,
    created_by: uuid.UUID,
    scheduled_date: date,
    start_time: time,
    duration_minutes: int = 45,
    status: AppointmentStatus = AppointmentStatus.SCHEDULED,
) -> Appointment:
    end_dt = datetime.combine(date(2000, 1, 1), start_time) + timedelta(minutes=duration_minutes)
    appointment = Appointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        therapist_id=therapist.id,
        scheduled_date=scheduled_date,
        start_time=start_time,
        end_time=end_dt.time(),
        duration_minutes=duration_minutes,
        status=status,
        appointment_source=AppointmentSource.MANUAL,
        created_by=created_by,
    )
    db_session.add(appointment)
    db_session.commit()
    db_session.refresh(appointment)
    return appointment
