"""
RouteCare AI - Therapist business logic.

A Therapist is a User (role=THERAPIST) plus a profile row - see
app/models/therapist.py. create_therapist is the only place either is
ever created, and it creates both atomically; update_therapist only
ever edits the existing pair, never creates a new user, per the
explicit "do not create duplicate user accounts" requirement.

Every query is scoped by clinic_id directly, matching patient_service's
tenant-isolation pattern (404, not 403, for a wrong-clinic id).
"""

import uuid
from typing import Literal

from sqlalchemy.orm import InstrumentedAttribute, Query, Session, joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import UserRole
from app.core.security import hash_password
from app.database.pagination import paginate
from app.models.therapist import Therapist
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.therapist import TherapistCreate, TherapistUpdate

SortBy = Literal["name", "created_at"]
SortOrder = Literal["asc", "desc"]


def _not_found() -> NotFoundError:
    return NotFoundError("Therapist was not found.", code="THERAPIST_NOT_FOUND")


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

    therapist = Therapist(
        clinic_id=clinic_id,
        user_id=user.id,
        license_type=data.license_type,
        phone=data.phone,
        home_address=data.home_address,
        home_latitude=data.home_latitude,
        home_longitude=data.home_longitude,
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

    for field in updates.keys() - user_fields:
        setattr(therapist, field, updates[field])

    db.commit()
    db.refresh(therapist)
    return therapist
