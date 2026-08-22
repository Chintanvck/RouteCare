"""
RouteCare AI - Shared test fixtures.

Tests run against an in-memory SQLite database (via app.database.types.GUID's
portable column type) rather than requiring a local Postgres instance.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers models with Base.metadata
from app.core.permissions import UserRole
from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.clinic import Clinic
from app.models.patient import Patient
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
