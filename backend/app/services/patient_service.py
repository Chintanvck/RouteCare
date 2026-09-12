"""
RouteCare AI - Patient business logic.

Every query is scoped by clinic_id directly in the WHERE clause (never
"load then check clinic_id") - patient records are called out
explicitly as sensitive PII in docs/09_Security_Privacy_Compliance.md,
so a wrong-clinic ID should be indistinguishable from a nonexistent one
(404 either way), rather than confirming the record exists elsewhere
via a 403 (which is how app.core.permissions.require_clinic_access
behaves, and remains the right default for less sensitive resources).

Geocoding lifecycle (Phase 5, see app.models.patient.GeocodingStatus):
- Coordinates supplied directly (create or update) are always treated
  as a manual override - MANUAL + location_verified=True - regardless
  of what the address text says. A human provided them; the system
  never second-guesses that.
- Otherwise, the address is geocoded automatically through
  app.services.geocoding.geocode_address, which has its own short
  timeout and never raises - `_geocode_safely` below is an extra safety
  net in case a provider implementation ever misbehaves, so a
  geocoding hiccup can never block patient create/update.
- Editing the address on an already `location_verified` patient does
  NOT trigger a silent re-geocode - a human confirmed those coordinates
  are correct, so an address typo fix shouldn't move the pin out from
  under them. Un-marking `location_verified` in the same request (or a
  prior one) opts back into automatic re-geocoding on the next address
  edit.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import InstrumentedAttribute, Query, Session

from app.core.exceptions import NotFoundError
from app.core.logging_config import app_logger
from app.database.pagination import paginate
from app.models.appointment import Appointment
from app.models.patient import GeocodingStatus, Patient
from app.schemas.common import PaginationParams
from app.schemas.patient import PatientCreate, PatientUpdate
from app.services import audit_service, geocoding

SortBy = Literal["name", "created_at", "zip_code"]
SortOrder = Literal["asc", "desc"]


def _not_found() -> NotFoundError:
    return NotFoundError("Patient was not found.", code="PATIENT_NOT_FOUND")


def _geocode_safely(
    *, clinic_id: uuid.UUID, address_line_1: str, city: str, state: str, zip_code: str
) -> geocoding.GeocodeResult | None:
    """geocoding.geocode_address already turns every provider failure mode into `None` rather than
    raising - this wrapper is only a last-resort safety net so a bug in a future provider
    implementation still can't block patient create/update."""
    try:
        return geocoding.geocode_address(
            clinic_id=clinic_id, address_line_1=address_line_1, city=city, state=state, zip_code=zip_code
        )
    except Exception:  # noqa: BLE001 - geocoding must never block this request
        app_logger.warning("patient_geocoding_unexpected_error", extra={"clinic_id": str(clinic_id)})
        return None


def create_patient(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    data: PatientCreate,
    source_system: str = "manual",
    actor_user_id: uuid.UUID | None = None,
) -> Patient:
    now = datetime.now(timezone.utc)

    if data.latitude is not None and data.longitude is not None:
        latitude, longitude = data.latitude, data.longitude
        geocoding_status = GeocodingStatus.MANUAL
        location_verified = True
        geocoded_at = now
    else:
        result = _geocode_safely(
            clinic_id=clinic_id,
            address_line_1=data.address_line_1,
            city=data.city,
            state=data.state,
            zip_code=data.zip_code,
        )
        location_verified = False
        if result is not None:
            latitude, longitude, geocoding_status, geocoded_at = (
                result.latitude,
                result.longitude,
                GeocodingStatus.GEOCODED,
                now,
            )
        else:
            latitude, longitude, geocoding_status, geocoded_at = None, None, GeocodingStatus.FAILED, None

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
        geocoding_status=geocoding_status,
        geocoded_at=geocoded_at,
        location_verified=location_verified,
        external_patient_id=data.external_patient_id,
        visit_duration_minutes=data.visit_duration_minutes,
        priority_level=data.priority_level,
        scheduling_notes=data.scheduling_notes,
        source_system=source_system,
    )
    db.add(patient)
    db.flush()
    audit_service.record(
        db, clinic_id=clinic_id, user_id=actor_user_id, action="PATIENT_CREATED", entity_type="PATIENT", entity_id=patient.id
    )
    db.commit()
    db.refresh(patient)
    return patient


def _active_patients_query(
    db: Session, *, clinic_id: uuid.UUID, restrict_to_therapist_id: uuid.UUID | None = None
) -> Query:
    """`restrict_to_therapist_id` scopes to patients the therapist has (or had) at least one
    appointment with - the "relationship" Phase 11 uses instead of a schema change, per its
    explicit "prefer fixing authorization using existing relationships" instruction: Patient has no
    therapist_id/assignment column of its own (see this module's own docstring history), but
    Appointment already links the two. Any status counts (including CANCELLED/NO_SHOW) - a
    therapist who was ever legitimately scheduled with this patient has legitimately seen their
    info before; this only ever narrows visibility, never a live authorization decision on
    scheduling itself (that's app.services.appointment_service's job)."""
    query = db.query(Patient).filter(Patient.clinic_id == clinic_id, Patient.deleted_at.is_(None))
    if restrict_to_therapist_id is not None:
        query = query.filter(
            Patient.id.in_(
                db.query(Appointment.patient_id).filter(Appointment.therapist_id == restrict_to_therapist_id)
            )
        )
    return query


def get_patient(
    db: Session, *, clinic_id: uuid.UUID, patient_id: uuid.UUID, restrict_to_therapist_id: uuid.UUID | None = None
) -> Patient:
    patient = (
        _active_patients_query(db, clinic_id=clinic_id, restrict_to_therapist_id=restrict_to_therapist_id)
        .filter(Patient.id == patient_id)
        .first()
    )
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
    restrict_to_therapist_id: uuid.UUID | None = None,
) -> tuple[list[Patient], int]:
    query = _active_patients_query(db, clinic_id=clinic_id, restrict_to_therapist_id=restrict_to_therapist_id)

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


def update_patient(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    data: PatientUpdate,
    actor_user_id: uuid.UUID | None = None,
) -> Patient:
    patient = get_patient(db, clinic_id=clinic_id, patient_id=patient_id)

    updates = data.model_dump(exclude_unset=True)
    explicit_verified = updates.pop("location_verified", None)
    manual_coords_supplied = (
        "latitude" in updates
        and "longitude" in updates
        and updates["latitude"] is not None
        and updates["longitude"] is not None
    )
    address_changed = bool({"address_line_1", "city", "state", "zip_code"} & updates.keys())

    for field, value in updates.items():
        setattr(patient, field, value)

    if explicit_verified is not None:
        patient.location_verified = explicit_verified

    now = datetime.now(timezone.utc)
    if manual_coords_supplied:
        patient.geocoding_status = GeocodingStatus.MANUAL
        patient.location_verified = True
        patient.geocoded_at = now
    elif address_changed and not patient.location_verified:
        result = _geocode_safely(
            clinic_id=clinic_id,
            address_line_1=patient.address_line_1,
            city=patient.city,
            state=patient.state,
            zip_code=patient.zip_code,
        )
        if result is not None:
            patient.latitude = result.latitude
            patient.longitude = result.longitude
            patient.geocoding_status = GeocodingStatus.GEOCODED
            patient.geocoded_at = now
        else:
            # The address changed and the old coordinates are for the old address - keeping them
            # would silently mispoint the patient, so they're cleared rather than left stale.
            patient.latitude = None
            patient.longitude = None
            patient.geocoding_status = GeocodingStatus.FAILED
            patient.geocoded_at = None

    if updates:
        # Field *names* only, never the values themselves - per this module's data-minimization
        # note, an audit trail for PII fields shouldn't become a second place that PII lives.
        audit_service.record(
            db,
            clinic_id=clinic_id,
            user_id=actor_user_id,
            action="PATIENT_UPDATED",
            entity_type="PATIENT",
            entity_id=patient.id,
            new_value={"changed_fields": sorted(updates.keys())},
        )
    db.commit()
    db.refresh(patient)
    return patient


def geocode_patient(db: Session, *, clinic_id: uuid.UUID, patient_id: uuid.UUID) -> tuple[Patient, str | None]:
    """Explicit re-geocode action (`POST /patients/{id}/geocode`) - retries geocoding from the
    patient's current address regardless of its current status, e.g. for a patient imported from
    Excel before geocoding was available, or one whose address previously failed to resolve.
    Returns the updated patient plus the provider's normalized address (not persisted - see
    app.models.patient's docstring on why normalized_address isn't a stored column), or None if
    the address still couldn't be geocoded.
    """
    patient = get_patient(db, clinic_id=clinic_id, patient_id=patient_id)

    result = _geocode_safely(
        clinic_id=clinic_id,
        address_line_1=patient.address_line_1,
        city=patient.city,
        state=patient.state,
        zip_code=patient.zip_code,
    )
    if result is None:
        patient.geocoding_status = GeocodingStatus.FAILED
        patient.geocoded_at = None
        db.commit()
        db.refresh(patient)
        return patient, None

    patient.latitude = result.latitude
    patient.longitude = result.longitude
    patient.geocoding_status = GeocodingStatus.GEOCODED
    patient.geocoded_at = datetime.now(timezone.utc)
    patient.location_verified = False
    db.commit()
    db.refresh(patient)
    return patient, result.normalized_address


def soft_delete_patient(
    db: Session, *, clinic_id: uuid.UUID, patient_id: uuid.UUID, actor_user_id: uuid.UUID | None = None
) -> None:
    patient = get_patient(db, clinic_id=clinic_id, patient_id=patient_id)
    patient.deleted_at = datetime.now(timezone.utc)
    audit_service.record(
        db, clinic_id=clinic_id, user_id=actor_user_id, action="PATIENT_DELETED", entity_type="PATIENT", entity_id=patient.id
    )
    db.commit()
