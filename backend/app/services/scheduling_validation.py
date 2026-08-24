"""
RouteCare AI - Scheduling validation.

Pure functions operating on already-fetched data (no DB session) so
they're trivially unit-testable and reusable identically by both the
real create/update path and the dry-run /appointments/validate endpoint -
there is exactly one implementation of "is this appointment allowed,"
never two that could drift apart.

Time ranges are half-open [start, end): two ranges overlap iff
`a.start < b.end and b.start < a.end`. An appointment ending exactly
when another starts is not a conflict.
"""

from dataclasses import dataclass
from datetime import time

from app.models.patient_availability import PatientAvailabilityPreference


@dataclass(frozen=True)
class TimeRange:
    start: time
    end: time


def _ranges_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    return a_start < b_end and b_start < a_end


def _format_time(t: time) -> str:
    """ "%-I" (no leading zero) is a glibc/Linux strftime extension not supported on Windows -
    format with %I then strip the leading zero manually so this works cross-platform."""
    formatted = t.strftime("%I:%M %p")
    return formatted.lstrip("0") or formatted


def check_overlap(existing: list[TimeRange], start_time: time, end_time: time) -> list[str]:
    """`existing` should already be filtered to the same therapist, same date, non-cancelled,
    excluding the appointment being updated (if any)."""
    for other in existing:
        if _ranges_overlap(start_time, end_time, other.start, other.end):
            return [
                f"Therapist already has an appointment from {_format_time(other.start)} "
                f"to {_format_time(other.end)}."
            ]
    return []


def check_therapist_working_hours(
    rules: list[TimeRange], breaks: list[TimeRange], start_time: time, end_time: time
) -> list[str]:
    """`rules` = is_available=True rows for the appointment's day_of_week; `breaks` = is_available=False
    rows for that same day. No rules at all for the day means the therapist doesn't work that day."""
    errors = []

    if not rules:
        errors.append("Therapist does not work on this day.")
    elif not any(rule.start <= start_time and end_time <= rule.end for rule in rules):
        errors.append("Appointment falls outside the therapist's working hours for this day.")

    for br in breaks:
        if _ranges_overlap(start_time, end_time, br.start, br.end):
            errors.append(
                f"Appointment overlaps the therapist's break ({_format_time(br.start)} - " f"{_format_time(br.end)})."
            )
            break

    return errors


def check_patient_availability(
    rules: list[tuple[TimeRange, PatientAvailabilityPreference]], start_time: time, end_time: time
) -> list[str]:
    """`rules` = all patient_availability rows for the appointment's day_of_week. No rows at all for
    the day means the patient has no configured constraint - treated as available, per the flexible
    default homecare scheduling needs (see app/models/patient_availability.py)."""
    if not rules:
        return []

    errors = []
    not_available = [r for r, pref in rules if pref == PatientAvailabilityPreference.NOT_AVAILABLE]
    permitted = [r for r, pref in rules if pref != PatientAvailabilityPreference.NOT_AVAILABLE]

    for window in not_available:
        if _ranges_overlap(start_time, end_time, window.start, window.end):
            errors.append("Appointment overlaps a time the patient marked as not available.")
            break

    if permitted and not any(r.start <= start_time and end_time <= r.end for r in permitted):
        errors.append("Appointment falls outside the patient's available hours for this day.")

    return errors


def check_duration_consistency(start_time: time, end_time: time, duration_minutes: int) -> list[str]:
    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = end_time.hour * 60 + end_time.minute
    if end_minutes <= start_minutes:
        return ["Appointment end time must be after the start time."]
    if end_minutes - start_minutes != duration_minutes:
        return ["Appointment duration does not match the start and end time."]
    return []
