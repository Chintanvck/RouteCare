"""
RouteCare AI - Appointment business logic.

`_validate` is the single source of truth for "is this appointment
allowed" - used identically by create, update, and the dry-run
POST /appointments/validate endpoint, so a slot that validation says is
fine is guaranteed to actually succeed on create (no drift between the
two).

Tenant isolation follows patient_service's pattern (404, not 403, for
a wrong-clinic id). Row-level restriction for THERAPIST-role callers
(their own appointments only) is handled here via `restrict_to_therapist_id`
rather than in the router, so there's one enforcement point rather than
relying on every call site to remember it.
"""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Query, Session, joinedload

from app.core.exceptions import BusinessRuleError, ForbiddenError, NotFoundError
from app.database.pagination import paginate
from app.models.appointment import Appointment, AppointmentSource, AppointmentStatus
from app.models.patient_availability import PatientAvailability
from app.models.therapist import Therapist
from app.models.therapist_availability import TherapistAvailability
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate
from app.schemas.common import PaginationParams
from app.services import audit_service, patient_service, therapist_service
from app.services.scheduling_validation import (
    TimeRange,
    check_overlap,
    check_patient_availability,
    check_therapist_working_hours,
)

_THERAPIST_UPDATABLE_FIELDS = {"scheduled_date", "start_time", "duration_minutes", "status"}


def _not_found() -> NotFoundError:
    return NotFoundError("Appointment was not found.", code="APPOINTMENT_NOT_FOUND")


def _compute_end_time(start_time: time, duration_minutes: int) -> time | None:
    """Returns None if the appointment would cross midnight - not a supported case (see
    check_duration_consistency's cousin logic; a home-health visit never spans two calendar days)."""
    start_dt = datetime.combine(date(2000, 1, 1), start_time)
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    if end_dt.date() != start_dt.date():
        return None
    return end_dt.time()


def _validate(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    therapist: Therapist,
    scheduled_date: date,
    start_time: time,
    duration_minutes: int,
    exclude_appointment_id: uuid.UUID | None = None,
) -> tuple[time | None, list[str]]:
    end_time = _compute_end_time(start_time, duration_minutes)
    if end_time is None:
        return None, ["Appointment cannot extend past midnight."]

    errors: list[str] = []

    if not therapist.is_active:
        errors.append("This therapist is not currently active.")

    day_of_week = scheduled_date.weekday()

    existing_query = db.query(Appointment).filter(
        Appointment.clinic_id == clinic_id,
        Appointment.therapist_id == therapist.id,
        Appointment.scheduled_date == scheduled_date,
        Appointment.status != AppointmentStatus.CANCELLED,
    )
    if exclude_appointment_id is not None:
        existing_query = existing_query.filter(Appointment.id != exclude_appointment_id)
    existing_ranges = [TimeRange(a.start_time, a.end_time) for a in existing_query.all()]
    errors += check_overlap(existing_ranges, start_time, end_time)

    availability_rows = (
        db.query(TherapistAvailability)
        .filter(TherapistAvailability.therapist_id == therapist.id, TherapistAvailability.day_of_week == day_of_week)
        .all()
    )
    working_rules = [TimeRange(r.start_time, r.end_time) for r in availability_rows if r.is_available]
    breaks = [TimeRange(r.start_time, r.end_time) for r in availability_rows if not r.is_available]
    errors += check_therapist_working_hours(working_rules, breaks, start_time, end_time)

    return end_time, errors


def _validate_patient_availability(
    db: Session, *, patient_id: uuid.UUID, scheduled_date: date, start_time: time, end_time: time
) -> list[str]:
    day_of_week = scheduled_date.weekday()
    rows = (
        db.query(PatientAvailability)
        .filter(PatientAvailability.patient_id == patient_id, PatientAvailability.day_of_week == day_of_week)
        .all()
    )
    rules = [(TimeRange(r.start_time, r.end_time), r.preference_type) for r in rows]
    return check_patient_availability(rules, start_time, end_time)


def validate_appointment(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    therapist_id: uuid.UUID,
    patient_id: uuid.UUID,
    scheduled_date: date,
    start_time: time,
    duration_minutes: int,
    exclude_appointment_id: uuid.UUID | None = None,
) -> list[str]:
    """Dry-run: returns the same errors create/update would raise, without persisting anything."""
    try:
        therapist = therapist_service.get_therapist(db, clinic_id=clinic_id, therapist_id=therapist_id)
    except NotFoundError:
        return ["Therapist was not found."]
    try:
        patient_service.get_patient(db, clinic_id=clinic_id, patient_id=patient_id)
    except NotFoundError:
        return ["Patient was not found."]

    end_time, errors = _validate(
        db,
        clinic_id=clinic_id,
        therapist=therapist,
        scheduled_date=scheduled_date,
        start_time=start_time,
        duration_minutes=duration_minutes,
        exclude_appointment_id=exclude_appointment_id,
    )
    if end_time is not None:
        errors += _validate_patient_availability(
            db, patient_id=patient_id, scheduled_date=scheduled_date, start_time=start_time, end_time=end_time
        )
    return errors


def create_appointment(
    db: Session, *, clinic_id: uuid.UUID, created_by: uuid.UUID, data: AppointmentCreate
) -> Appointment:
    therapist = therapist_service.get_therapist(db, clinic_id=clinic_id, therapist_id=data.therapist_id)
    patient = patient_service.get_patient(db, clinic_id=clinic_id, patient_id=data.patient_id)

    end_time, errors = _validate(
        db,
        clinic_id=clinic_id,
        therapist=therapist,
        scheduled_date=data.scheduled_date,
        start_time=data.start_time,
        duration_minutes=data.duration_minutes,
    )
    if end_time is not None:
        errors += _validate_patient_availability(
            db,
            patient_id=patient.id,
            scheduled_date=data.scheduled_date,
            start_time=data.start_time,
            end_time=end_time,
        )
    if errors:
        raise BusinessRuleError(" ".join(errors), code="APPOINTMENT_VALIDATION_FAILED", details={"errors": errors})

    appointment = Appointment(
        clinic_id=clinic_id,
        patient_id=patient.id,
        therapist_id=therapist.id,
        scheduled_date=data.scheduled_date,
        start_time=data.start_time,
        end_time=end_time,
        duration_minutes=data.duration_minutes,
        status=AppointmentStatus.SCHEDULED,
        appointment_source=AppointmentSource.MANUAL,
        created_by=created_by,
    )
    db.add(appointment)
    db.flush()
    audit_service.record(
        db,
        clinic_id=clinic_id,
        user_id=created_by,
        action="APPOINTMENT_CREATED",
        entity_type="APPOINTMENT",
        entity_id=appointment.id,
        new_value={"scheduled_date": data.scheduled_date.isoformat(), "start_time": data.start_time.isoformat()},
    )
    db.commit()
    db.refresh(appointment)
    return appointment


def _base_query(db: Session, *, clinic_id: uuid.UUID) -> Query:
    return (
        db.query(Appointment)
        .filter(Appointment.clinic_id == clinic_id)
        .options(
            joinedload(Appointment.patient),
            joinedload(Appointment.therapist).joinedload(Therapist.user),
        )
    )


def get_appointment(
    db: Session, *, clinic_id: uuid.UUID, appointment_id: uuid.UUID, restrict_to_therapist_id: uuid.UUID | None = None
) -> Appointment:
    appointment = _base_query(db, clinic_id=clinic_id).filter(Appointment.id == appointment_id).first()
    if appointment is None:
        raise _not_found()
    if restrict_to_therapist_id is not None and appointment.therapist_id != restrict_to_therapist_id:
        raise _not_found()
    return appointment


def list_appointments(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    pagination: PaginationParams,
    start_date: date | None = None,
    end_date: date | None = None,
    therapist_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    status: AppointmentStatus | None = None,
    restrict_to_therapist_id: uuid.UUID | None = None,
) -> tuple[list[Appointment], int]:
    query = _base_query(db, clinic_id=clinic_id)

    effective_therapist_id = restrict_to_therapist_id if restrict_to_therapist_id is not None else therapist_id
    if effective_therapist_id is not None:
        query = query.filter(Appointment.therapist_id == effective_therapist_id)
    if patient_id is not None:
        query = query.filter(Appointment.patient_id == patient_id)
    if status is not None:
        query = query.filter(Appointment.status == status)
    if start_date is not None:
        query = query.filter(Appointment.scheduled_date >= start_date)
    if end_date is not None:
        query = query.filter(Appointment.scheduled_date <= end_date)

    query = query.order_by(Appointment.scheduled_date.asc(), Appointment.start_time.asc())
    return paginate(query, pagination)


def update_appointment(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    appointment_id: uuid.UUID,
    data: AppointmentUpdate,
    current_user: User,
    restrict_to_therapist_id: uuid.UUID | None = None,
) -> Appointment:
    appointment = get_appointment(
        db, clinic_id=clinic_id, appointment_id=appointment_id, restrict_to_therapist_id=restrict_to_therapist_id
    )
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        return appointment

    old_scheduled_date = appointment.scheduled_date
    old_start_time = appointment.start_time
    old_status = appointment.status

    if restrict_to_therapist_id is not None:
        disallowed = set(updates.keys()) - _THERAPIST_UPDATABLE_FIELDS
        if disallowed:
            raise ForbiddenError(
                "Therapists can only change the date, time, or status of their own appointments.",
                code="APPOINTMENT_FIELD_NOT_ALLOWED",
            )

    new_therapist_id = updates.get("therapist_id", appointment.therapist_id)
    new_patient_id = updates.get("patient_id", appointment.patient_id)
    new_scheduled_date = updates.get("scheduled_date", appointment.scheduled_date)
    new_start_time = updates.get("start_time", appointment.start_time)
    new_duration = updates.get("duration_minutes", appointment.duration_minutes)

    time_or_assignment_changed = any(
        field in updates for field in ("therapist_id", "patient_id", "scheduled_date", "start_time", "duration_minutes")
    )

    if time_or_assignment_changed:
        therapist = therapist_service.get_therapist(db, clinic_id=clinic_id, therapist_id=new_therapist_id)
        patient = patient_service.get_patient(db, clinic_id=clinic_id, patient_id=new_patient_id)

        end_time, errors = _validate(
            db,
            clinic_id=clinic_id,
            therapist=therapist,
            scheduled_date=new_scheduled_date,
            start_time=new_start_time,
            duration_minutes=new_duration,
            exclude_appointment_id=appointment.id,
        )
        if end_time is not None:
            errors += _validate_patient_availability(
                db,
                patient_id=patient.id,
                scheduled_date=new_scheduled_date,
                start_time=new_start_time,
                end_time=end_time,
            )
        if errors:
            raise BusinessRuleError(" ".join(errors), code="APPOINTMENT_VALIDATION_FAILED", details={"errors": errors})
        # _validate() only ever returns end_time=None alongside a non-empty errors list (the
        # "crosses midnight" case), which would have raised above - so end_time is real here.
        assert end_time is not None

        appointment.therapist_id = therapist.id
        appointment.patient_id = patient.id
        appointment.scheduled_date = new_scheduled_date
        appointment.start_time = new_start_time
        appointment.duration_minutes = new_duration
        appointment.end_time = end_time

    if "status" in updates:
        appointment.status = updates["status"]

    old_value: dict[str, str] = {}
    new_value: dict[str, str] = {}
    if old_scheduled_date != appointment.scheduled_date or old_start_time != appointment.start_time:
        old_value["scheduled_at"] = f"{old_scheduled_date.isoformat()} {old_start_time.isoformat()}"
        new_value["scheduled_at"] = f"{appointment.scheduled_date.isoformat()} {appointment.start_time.isoformat()}"
    if old_status != appointment.status:
        old_value["status"] = old_status.value
        new_value["status"] = appointment.status.value
    audit_service.record(
        db,
        clinic_id=clinic_id,
        user_id=current_user.id,
        action="APPOINTMENT_UPDATED",
        entity_type="APPOINTMENT",
        entity_id=appointment.id,
        old_value=old_value or None,
        new_value=new_value or {"changed_fields": sorted(updates.keys())},
    )

    db.commit()
    db.refresh(appointment)
    return appointment


def cancel_appointment(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    appointment_id: uuid.UUID,
    restrict_to_therapist_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    appointment = get_appointment(
        db, clinic_id=clinic_id, appointment_id=appointment_id, restrict_to_therapist_id=restrict_to_therapist_id
    )
    appointment.status = AppointmentStatus.CANCELLED
    audit_service.record(
        db,
        clinic_id=clinic_id,
        user_id=actor_user_id,
        action="APPOINTMENT_CANCELLED",
        entity_type="APPOINTMENT",
        entity_id=appointment.id,
    )
    db.commit()
