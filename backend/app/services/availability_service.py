"""
RouteCare AI - Availability business logic.

Both therapist and patient availability use a "replace the whole weekly
set" write model (matching docs/05_API_Design.md's PUT /therapists/{id}/availability
semantics) rather than incremental add/remove of individual rules -
simpler to reason about and matches how a clinic actually edits a
weekly schedule (they re-specify the whole week, not patch one slot).
"""

import uuid

from sqlalchemy.orm import Session

from app.models.patient_availability import PatientAvailability
from app.models.therapist_availability import TherapistAvailability
from app.schemas.availability import PatientAvailabilityRuleInput, TherapistAvailabilityRuleInput


def get_therapist_availability(db: Session, *, therapist_id: uuid.UUID) -> list[TherapistAvailability]:
    return (
        db.query(TherapistAvailability)
        .filter(TherapistAvailability.therapist_id == therapist_id)
        .order_by(TherapistAvailability.day_of_week.asc(), TherapistAvailability.start_time.asc())
        .all()
    )


def set_therapist_availability(
    db: Session, *, therapist_id: uuid.UUID, rules: list[TherapistAvailabilityRuleInput]
) -> list[TherapistAvailability]:
    db.query(TherapistAvailability).filter(TherapistAvailability.therapist_id == therapist_id).delete()
    for rule in rules:
        db.add(
            TherapistAvailability(
                therapist_id=therapist_id,
                day_of_week=rule.day_of_week,
                start_time=rule.start_time,
                end_time=rule.end_time,
                is_available=rule.is_available,
            )
        )
    db.commit()
    return get_therapist_availability(db, therapist_id=therapist_id)


def get_patient_availability(db: Session, *, patient_id: uuid.UUID) -> list[PatientAvailability]:
    return (
        db.query(PatientAvailability)
        .filter(PatientAvailability.patient_id == patient_id)
        .order_by(PatientAvailability.day_of_week.asc(), PatientAvailability.start_time.asc())
        .all()
    )


def set_patient_availability(
    db: Session, *, patient_id: uuid.UUID, rules: list[PatientAvailabilityRuleInput]
) -> list[PatientAvailability]:
    db.query(PatientAvailability).filter(PatientAvailability.patient_id == patient_id).delete()
    for rule in rules:
        db.add(
            PatientAvailability(
                patient_id=patient_id,
                day_of_week=rule.day_of_week,
                start_time=rule.start_time,
                end_time=rule.end_time,
                preference_type=rule.preference_type,
            )
        )
    db.commit()
    return get_patient_availability(db, patient_id=patient_id)
