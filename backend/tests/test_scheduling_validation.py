"""Unit tests for app.services.scheduling_validation - pure functions, no DB needed."""

from datetime import time

from app.models.patient_availability import PatientAvailabilityPreference as Pref
from app.services.scheduling_validation import (
    TimeRange,
    check_duration_consistency,
    check_overlap,
    check_patient_availability,
    check_therapist_working_hours,
)

# --- overlap ---


def test_no_overlap_with_empty_schedule() -> None:
    assert check_overlap([], time(9, 0), time(10, 0)) == []


def test_overlap_detected() -> None:
    existing = [TimeRange(time(13, 0), time(14, 0))]
    errors = check_overlap(existing, time(13, 30), time(14, 30))
    assert errors == ["Therapist already has an appointment from 1:00 PM to 2:00 PM."]


def test_back_to_back_appointments_do_not_overlap() -> None:
    """[start, end) is half-open - ending exactly when another starts is fine."""
    existing = [TimeRange(time(9, 0), time(10, 0))]
    assert check_overlap(existing, time(10, 0), time(11, 0)) == []
    assert check_overlap(existing, time(8, 0), time(9, 0)) == []


def test_new_appointment_fully_inside_existing_overlaps() -> None:
    existing = [TimeRange(time(9, 0), time(17, 0))]
    assert check_overlap(existing, time(12, 0), time(13, 0)) != []


def test_new_appointment_fully_containing_existing_overlaps() -> None:
    existing = [TimeRange(time(12, 0), time(13, 0))]
    assert check_overlap(existing, time(9, 0), time(17, 0)) != []


# --- therapist working hours / breaks ---


def test_within_working_hours_no_errors() -> None:
    rules = [TimeRange(time(9, 0), time(17, 0))]
    assert check_therapist_working_hours(rules, [], time(10, 0), time(11, 0)) == []


def test_no_rules_for_day_means_day_off() -> None:
    errors = check_therapist_working_hours([], [], time(10, 0), time(11, 0))
    assert errors == ["Therapist does not work on this day."]


def test_outside_working_hours_rejected() -> None:
    rules = [TimeRange(time(9, 0), time(17, 0))]
    errors = check_therapist_working_hours(rules, [], time(17, 30), time(18, 30))
    assert "outside the therapist's working hours" in errors[0]


def test_appointment_overlapping_break_rejected() -> None:
    rules = [TimeRange(time(9, 0), time(17, 0))]
    breaks = [TimeRange(time(12, 0), time(13, 0))]
    errors = check_therapist_working_hours(rules, breaks, time(12, 30), time(13, 30))
    assert any("break" in e for e in errors)


def test_appointment_around_break_is_fine() -> None:
    rules = [TimeRange(time(9, 0), time(17, 0))]
    breaks = [TimeRange(time(12, 0), time(13, 0))]
    assert check_therapist_working_hours(rules, breaks, time(9, 0), time(12, 0)) == []
    assert check_therapist_working_hours(rules, breaks, time(13, 0), time(14, 0)) == []


def test_multiple_working_windows_same_day() -> None:
    """A day split by a break can be modeled as two is_available=True rows instead of one + a break row."""
    rules = [TimeRange(time(9, 0), time(12, 0)), TimeRange(time(13, 0), time(17, 0))]
    assert check_therapist_working_hours(rules, [], time(9, 30), time(10, 30)) == []
    assert check_therapist_working_hours(rules, [], time(13, 30), time(14, 30)) == []
    assert check_therapist_working_hours(rules, [], time(12, 0), time(13, 0)) != []


# --- patient availability ---


def test_patient_no_rules_means_flexible() -> None:
    assert check_patient_availability([], time(3, 0), time(4, 0)) == []


def test_patient_not_available_window_rejected() -> None:
    rules = [(TimeRange(time(12, 0), time(13, 0)), Pref.NOT_AVAILABLE)]
    errors = check_patient_availability(rules, time(12, 30), time(13, 30))
    assert any("not available" in e for e in errors)


def test_patient_available_window_permits_scheduling() -> None:
    rules = [(TimeRange(time(9, 0), time(17, 0)), Pref.AVAILABLE)]
    assert check_patient_availability(rules, time(10, 0), time(11, 0)) == []


def test_patient_preferred_window_permits_scheduling() -> None:
    rules = [(TimeRange(time(9, 0), time(17, 0)), Pref.PREFERRED)]
    assert check_patient_availability(rules, time(10, 0), time(11, 0)) == []


def test_patient_outside_configured_window_rejected() -> None:
    rules = [(TimeRange(time(9, 0), time(12, 0)), Pref.AVAILABLE)]
    errors = check_patient_availability(rules, time(14, 0), time(15, 0))
    assert any("outside the patient's available hours" in e for e in errors)


# --- duration consistency ---


def test_duration_matches_start_end() -> None:
    assert check_duration_consistency(time(9, 0), time(9, 45), 45) == []


def test_duration_mismatch_rejected() -> None:
    assert check_duration_consistency(time(9, 0), time(9, 45), 30) != []


def test_end_before_start_rejected() -> None:
    assert check_duration_consistency(time(10, 0), time(9, 0), 30) != []
