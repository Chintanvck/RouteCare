"""
RouteCare AI - Therapist business logic.

A Therapist is a User (role=THERAPIST) plus a profile row - see
app/models/therapist.py. create_therapist is the only place either is
ever created, and it creates both atomically; update_therapist only
ever edits the existing pair, never creates a new user, per the
explicit "do not create duplicate user accounts" requirement.

Every query is scoped by clinic_id directly, matching patient_service's
tenant-isolation pattern (404, not 403, for a wrong-clinic id).

`home_address` geocoding follows the exact same lifecycle as
patient_service's (Phase 5) - see that module's docstring for the full
reasoning on manual overrides vs. automatic re-geocoding.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import InstrumentedAttribute, Query, Session, joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging_config import app_logger
from app.core.permissions import UserRole
from app.core.security import hash_password
from app.database.pagination import paginate
from app.models.patient import GeocodingStatus
from app.models.therapist import Therapist
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.therapist import TherapistCreate, TherapistUpdate
from app.services import geocoding

SortBy = Literal["name", "created_at"]
SortOrder = Literal["asc", "desc"]


def _not_found() -> NotFoundError:
    return NotFoundError("Therapist was not found.", code="THERAPIST_NOT_FOUND")


def _geocode_safely(*, clinic_id: uuid.UUID, address: str) -> geocoding.GeocodeResult | None:
    """Same safety net as patient_service._geocode_safely. Therapist home_address is a single
    free-text field (per app/models/therapist.py), passed straight through as the address line -
    Nominatim's free-form query handles that fine."""
    try:
        return geocoding.geocode_address(clinic_id=clinic_id, address_line_1=address, city="", state="", zip_code="")
    except Exception:  # noqa: BLE001 - geocoding must never block this request
        app_logger.warning("therapist_geocoding_unexpected_error", extra={"clinic_id": str(clinic_id)})
        return None


def create_therapist(db: Session, *, clinic_id: uuid.UUID, data: TherapistCreate) -> Therapist:
    existing = db.query(User).filter(User.email == data.email).first()
    if existing is not None:
        raise ConflictError("An account with that email already exists.", code="EMAIL_ALREADY_EXISTS")

    user = User(
        clinic_id=clinic_id,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.THERAPIST,
        is_active=True,
    )
    db.add(user)
    db.flush()

    now = datetime.now(timezone.utc)
    if data.home_latitude is not None and data.home_longitude is not None:
        home_latitude, home_longitude = data.home_latitude, data.home_longitude
        geocoding_status = GeocodingStatus.MANUAL
        location_verified = True
        geocoded_at = now
    elif data.home_address:
        result = _geocode_safely(clinic_id=clinic_id, address=data.home_address)
        location_verified = False
        if result is not None:
            home_latitude, home_longitude, geocoding_status, geocoded_at = (
                result.latitude,
                result.longitude,
                GeocodingStatus.GEOCODED,
                now,
            )
        else:
            home_latitude, home_longitude, geocoding_status, geocoded_at = None, None, GeocodingStatus.FAILED, None
    else:
        home_latitude, home_longitude, geocoding_status, geocoded_at, location_verified = (
            None,
            None,
            GeocodingStatus.PENDING,
            None,
            False,
        )

    therapist = Therapist(
        clinic_id=clinic_id,
        user_id=user.id,
        license_type=data.license_type,
        phone=data.phone,
        home_address=data.home_address,
        home_latitude=home_latitude,
        home_longitude=home_longitude,
        geocoding_status=geocoding_status,
        geocoded_at=geocoded_at,
        location_verified=location_verified,
        max_daily_hours=data.max_daily_hours,
        max_drive_time_minutes=data.max_drive_time_minutes,
    )
    db.add(therapist)
    db.commit()
    db.refresh(therapist)
    return therapist


def _base_query(db: Session, *, clinic_id: uuid.UUID) -> Query:
    return (
        db.query(Therapist)
        .join(User, Therapist.user_id == User.id)
        .filter(Therapist.clinic_id == clinic_id)
        .options(joinedload(Therapist.user))
    )


def get_therapist(db: Session, *, clinic_id: uuid.UUID, therapist_id: uuid.UUID) -> Therapist:
    therapist = _base_query(db, clinic_id=clinic_id).filter(Therapist.id == therapist_id).first()
    if therapist is None:
        raise _not_found()
    return therapist


def get_therapist_by_user_id(db: Session, *, clinic_id: uuid.UUID, user_id: uuid.UUID) -> Therapist | None:
    return _base_query(db, clinic_id=clinic_id).filter(Therapist.user_id == user_id).first()


def list_therapists(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    pagination: PaginationParams,
    search: str | None = None,
    is_active: bool | None = None,
    sort_by: SortBy = "name",
    sort_order: SortOrder = "asc",
) -> tuple[list[Therapist], int]:
    query = _base_query(db, clinic_id=clinic_id)

    if search:
        like = f"%{search.strip()}%"
        query = query.filter((User.first_name.ilike(like)) | (User.last_name.ilike(like)))

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    column: InstrumentedAttribute
    if sort_by == "created_at":
        column = Therapist.created_at
    else:
        column = User.last_name

    query = query.order_by(column.desc() if sort_order == "desc" else column.asc())

    return paginate(query, pagination)


def update_therapist(db: Session, *, clinic_id: uuid.UUID, therapist_id: uuid.UUID, data: TherapistUpdate) -> Therapist:
    therapist = get_therapist(db, clinic_id=clinic_id, therapist_id=therapist_id)
    updates = data.model_dump(exclude_unset=True)

    user_fields = {"first_name", "last_name", "email", "is_active"}
    for field in user_fields & updates.keys():
        if field == "email" and updates[field] != therapist.user.email:
            existing = db.query(User).filter(User.email == updates[field]).first()
            if existing is not None:
                raise ConflictError("An account with that email already exists.", code="EMAIL_ALREADY_EXISTS")
        setattr(therapist.user, field, updates[field])

    explicit_verified = updates.pop("location_verified", None)
    manual_coords_supplied = (
        "home_latitude" in updates
        and "home_longitude" in updates
        and updates["home_latitude"] is not None
        and updates["home_longitude"] is not None
    )
    address_changed = "home_address" in updates

    for field in updates.keys() - user_fields:
        setattr(therapist, field, updates[field])

    if explicit_verified is not None:
        therapist.location_verified = explicit_verified

    now = datetime.now(timezone.utc)
    if manual_coords_supplied:
        therapist.geocoding_status = GeocodingStatus.MANUAL
        therapist.location_verified = True
        therapist.geocoded_at = now
    elif address_changed and not therapist.location_verified:
        result = (
            _geocode_safely(clinic_id=clinic_id, address=therapist.home_address) if therapist.home_address else None
        )
        if result is not None:
            therapist.home_latitude = result.latitude
            therapist.home_longitude = result.longitude
            therapist.geocoding_status = GeocodingStatus.GEOCODED
            therapist.geocoded_at = now
        else:
            therapist.home_latitude = None
            therapist.home_longitude = None
            therapist.geocoding_status = (
                GeocodingStatus.PENDING if not therapist.home_address else GeocodingStatus.FAILED
            )
            therapist.geocoded_at = None

    db.commit()
    db.refresh(therapist)
    return therapist


def geocode_therapist(db: Session, *, clinic_id: uuid.UUID, therapist_id: uuid.UUID) -> tuple[Therapist, str | None]:
    """Explicit re-geocode action (`POST /therapists/{id}/geocode`) - mirrors
    patient_service.geocode_patient."""
    therapist = get_therapist(db, clinic_id=clinic_id, therapist_id=therapist_id)

    if not therapist.home_address:
        raise ConflictError("This therapist has no home address to geocode.", code="NO_ADDRESS_TO_GEOCODE")

    result = _geocode_safely(clinic_id=clinic_id, address=therapist.home_address)
    if result is None:
        therapist.geocoding_status = GeocodingStatus.FAILED
        therapist.geocoded_at = None
        db.commit()
        db.refresh(therapist)
        return therapist, None

    therapist.home_latitude = result.latitude
    therapist.home_longitude = result.longitude
    therapist.geocoding_status = GeocodingStatus.GEOCODED
    therapist.geocoded_at = datetime.now(timezone.utc)
    therapist.location_verified = False
    db.commit()
    db.refresh(therapist)
    return therapist, result.normalized_address
