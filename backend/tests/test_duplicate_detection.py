"""Tests for app.services.duplicate_detection."""

import uuid

from app.services.duplicate_detection import (
    PatientSignature,
    WithinFileDuplicateTracker,
    match_against_existing_patients,
)


def _sig(**overrides) -> PatientSignature:
    defaults = dict(
        patient_id=uuid.uuid4(), first_name="Mary", last_name="Smith", email=None, phone=None, zip_code="07030"
    )
    defaults.update(overrides)
    return PatientSignature(**defaults)


def test_exact_match_by_email() -> None:
    existing = [_sig(email="mary@example.com")]
    match = match_against_existing_patients(
        first_name="Someone",
        last_name="Else",
        email="Mary@Example.com",
        phone=None,
        zip_code="99999",
        existing=existing,
    )
    assert match is not None
    assert match.kind == "EXACT"
    assert match.confidence == 100.0


def test_exact_match_by_phone_ignoring_formatting() -> None:
    existing = [_sig(phone="(201) 555-0100")]
    match = match_against_existing_patients(
        first_name="X", last_name="Y", email=None, phone="201.555.0100", zip_code="00000", existing=existing
    )
    assert match is not None
    assert match.kind == "EXACT"


def test_exact_match_by_name_and_zip() -> None:
    existing = [_sig(first_name="Mary", last_name="Smith", zip_code="07030")]
    match = match_against_existing_patients(
        first_name="mary", last_name="smith", email=None, phone=None, zip_code="07030", existing=existing
    )
    assert match is not None
    assert match.kind == "EXACT"


def test_no_match_returns_none() -> None:
    existing = [_sig(first_name="Mary", last_name="Smith", zip_code="07030")]
    match = match_against_existing_patients(
        first_name="John", last_name="Doe", email=None, phone=None, zip_code="10001", existing=existing
    )
    assert match is None


def test_probable_match_requires_name_similarity_and_same_zip() -> None:
    existing = [_sig(first_name="John", last_name="Smith", zip_code="07030")]
    match = match_against_existing_patients(
        first_name="Jon", last_name="Smith", email=None, phone=None, zip_code="07030", existing=existing
    )
    assert match is not None
    assert match.kind == "PROBABLE"
    assert 0 < match.confidence < 100


def test_name_similarity_alone_without_corroborating_signal_is_not_a_match() -> None:
    """Two different people who happen to share a similar name in a different ZIP must NOT match -
    this is the explicit 'do not assume duplicate based on name alone' requirement."""
    existing = [_sig(first_name="John", last_name="Smith", zip_code="07030")]
    match = match_against_existing_patients(
        first_name="John", last_name="Smith", email=None, phone=None, zip_code="90210", existing=existing
    )
    assert match is None


def test_dissimilar_names_in_same_zip_do_not_match() -> None:
    existing = [_sig(first_name="John", last_name="Smith", zip_code="07030")]
    match = match_against_existing_patients(
        first_name="Alice", last_name="Johnson", email=None, phone=None, zip_code="07030", existing=existing
    )
    assert match is None


# --- Within-file duplicate tracker ---


def test_within_file_tracker_flags_repeated_email() -> None:
    tracker = WithinFileDuplicateTracker()
    first = tracker.check_and_register(
        1, first_name="A", last_name="B", email="dup@example.com", phone=None, zip_code=None
    )
    second = tracker.check_and_register(
        5, first_name="C", last_name="D", email="dup@example.com", phone=None, zip_code=None
    )
    assert first is None
    assert second == 1


def test_within_file_tracker_flags_repeated_name_and_zip() -> None:
    tracker = WithinFileDuplicateTracker()
    tracker.check_and_register(1, first_name="Mary", last_name="Smith", email=None, phone=None, zip_code="07030")
    match = tracker.check_and_register(
        2, first_name="Mary", last_name="Smith", email=None, phone=None, zip_code="07030"
    )
    assert match == 1


def test_within_file_tracker_does_not_flag_distinct_rows() -> None:
    tracker = WithinFileDuplicateTracker()
    tracker.check_and_register(1, first_name="Mary", last_name="Smith", email=None, phone=None, zip_code="07030")
    match = tracker.check_and_register(2, first_name="John", last_name="Doe", email=None, phone=None, zip_code="10001")
    assert match is None
