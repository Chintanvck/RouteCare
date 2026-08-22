"""
RouteCare AI - Patient business logic.

Every query is scoped by clinic_id directly in the WHERE clause (never
"load then check clinic_id") - patient records are called out
explicitly as sensitive PII in docs/09_Security_Privacy_Compliance.md,
so a wrong-clinic ID should be indistinguishable from a nonexistent one
(404 either way), rather than confirming the record exists elsewhere
via a 403 (which is how app.core.permissions.require_clinic_access
behaves, and remains the right default for less sensitive resources).
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import InstrumentedAttribute, Query, Session

from app.core.exceptions import NotFoundError
from app.database.pagination import paginate
from app.models.patient import Patient
from app.schemas.common import PaginationParams
from app.schemas.patient import PatientCreate, PatientUpdate
from app.services.geocoding import get_geocoding_provider

SortBy = Literal["name", "created_at", "zip_code"]
SortOrder = Literal["asc", "desc"]


def _not_found() -> NotFoundError:
    return NotFoundError("Patient was not found.", code="PATIENT_NOT_FOUND")


def _maybe_geocode(
    *, latitude: float | None, longitude: float | None, address_line_1: str, city: str, state: str, zip_code: str
) -> tuple[float | None, float | None]:
    if latitude is not None and longitude is not None:
        return latitude, longitude
    result = get_geocoding_provider().geocode(address_line_1=address_line_1, city=city, state=state, zip_code=zip_code)
    if result is None:
        return latitude, longitude
    return result.latitude, result.longitude


def create_patient(db: Session, *, clinic_id: uuid.UUID, data: PatientCreate) -> Patient:
    latitude, longitude = _maybe_geocode(
        latitude=data.latitude,
        longitude=data.longitude,
        address_line_1=data.address_line_1,
        city=data.city,
        state=data.state,
        zip_code=data.zip_code,
    )

    patient = Patient(
        clinic_id=clinic_id,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        email=data.email,
        address_line_1=data.address_line_1,
        address_line_2=data.address_line_2,
        city=data.city,
        state=data.state,
        zip_code=data.zip_code,
        latitude=latitude,
        longitude=longitude,
        external_patient_id=data.external_patient_id,
        visit_duration_minutes=data.visit_duration_minutes,
        priority_level=data.priority_level,
        scheduling_notes=data.scheduling_notes,
        source_system="manual",
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def _active_patients_query(db: Session, *, clinic_id: uuid.UUID) -> Query:
    return db.query(Patient).filter(Patient.clinic_id == clinic_id, Patient.deleted_at.is_(None))


def get_patient(db: Session, *, clinic_id: uuid.UUID, patient_id: uuid.UUID) -> Patient:
    patient = _active_patients_query(db, clinic_id=clinic_id).filter(Patient.id == patient_id).first()
    if patient is None:
        raise _not_found()
    return patient


def list_patients(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    pagination: PaginationParams,
    search: str | None = None,
    zip_code: str | None = None,
    sort_by: SortBy = "created_at",
    sort_order: SortOrder = "desc",
) -> tuple[list[Patient], int]:
    query = _active_patients_query(db, clinic_id=clinic_id)

    if search:
        like = f"%{search.strip()}%"
        query = query.filter((Patient.first_name.ilike(like)) | (Patient.last_name.ilike(like)))

    if zip_code:
        query = query.filter(Patient.zip_code == zip_code)

    columns: tuple[InstrumentedAttribute, ...]
    if sort_by == "name":
        columns = (Patient.last_name, Patient.first_name)
    elif sort_by == "zip_code":
        columns = (Patient.zip_code,)
    else:
        columns = (Patient.created_at,)

    if sort_order == "desc":
        query = query.order_by(*(c.desc() for c in columns))
    else:
        query = query.order_by(*(c.asc() for c in columns))

    return paginate(query, pagination)


def update_patient(db: Session, *, clinic_id: uuid.UUID, patient_id: uuid.UUID, data: PatientUpdate) -> Patient:
    patient = get_patient(db, clinic_id=clinic_id, patient_id=patient_id)

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(patient, field, value)

    if (
        "latitude" in updates
        or "longitude" in updates
        or any(f in updates for f in ("address_line_1", "city", "state", "zip_code"))
    ):
        latitude, longitude = _maybe_geocode(
            latitude=patient.latitude,
            longitude=patient.longitude,
            address_line_1=patient.address_line_1,
            city=patient.city,
            state=patient.state,
            zip_code=patient.zip_code,
        )
        patient.latitude = latitude
        patient.longitude = longitude

    db.commit()
    db.refresh(patient)
    return patient


def soft_delete_patient(db: Session, *, clinic_id: uuid.UUID, patient_id: uuid.UUID) -> None:
    patient = get_patient(db, clinic_id=clinic_id, patient_id=patient_id)
    patient.deleted_at = datetime.now(timezone.utc)
    db.commit()
