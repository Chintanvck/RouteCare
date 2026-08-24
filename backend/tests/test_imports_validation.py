"""
Tests for app.services.import_service.run_row_validation, called
directly (not through Celery) against the test's SQLite session - see
conftest.py's module docstring on why the Celery task itself can't
target the test DB.
"""

from sqlalchemy.orm import Session

from app.models.import_job import ImportJob, ImportStatus
from app.models.import_row import ImportRow, RowClassification
from app.models.import_row_error import ImportRowError
from app.services import import_service
from tests.conftest import build_theraoffice_xlsx, make_patient


def _upload(db_session: Session, clinic, admin, rows: list[list]) -> ImportJob:
    content = build_theraoffice_xlsx(rows)
    job, _mapping = import_service.upload_import(
        db_session,
        clinic_id=clinic.id,
        uploaded_by=admin.id,
        filename="patients.xlsx",
        content=content,
        source_system="theraoffice",
    )
    return job


_VALID_MAPPING = {
    "full_name": "Patient Full Name",
    "phone": "Phone",
    "email": "Email",
    "address_line_1": "Address",
    "city": "City",
    "state": "State",
    "zip_code": "ZIP",
}


def test_validation_classifies_valid_rows(db_session: Session, clinic, make_admin) -> None:
    admin = make_admin
    job = _upload(
        db_session,
        clinic,
        admin,
        [["Mary Smith", "201-555-0100", "mary@example.com", "123 Main St", "Hoboken", "NJ", "07030"]],
    )
    job.column_mapping = _VALID_MAPPING
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)

    rows = db_session.query(ImportRow).filter(ImportRow.import_id == job.id).all()
    assert len(rows) == 1
    assert rows[0].classification == RowClassification.VALID
    assert rows[0].mapped_data["first_name"] == "Mary"
    assert rows[0].mapped_data["last_name"] == "Smith"

    db_session.refresh(job)
    assert job.status == ImportStatus.PENDING
    assert job.total_records == 1
    assert job.valid_records == 1
    assert job.new_records == 1
    assert job.invalid_records == 0


def test_validation_flags_missing_required_field(db_session: Session, clinic, make_admin) -> None:
    job = _upload(db_session, clinic, make_admin, [["", "201-555-0100", "", "123 Main St", "Hoboken", "NJ", "07030"]])
    job.column_mapping = _VALID_MAPPING
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)

    row = db_session.query(ImportRow).filter(ImportRow.import_id == job.id).one()
    assert row.classification == RowClassification.INVALID
    assert row.errors
    assert any("required" in e["message"].lower() for e in row.errors)

    errors = db_session.query(ImportRowError).filter(ImportRowError.import_id == job.id).all()
    assert len(errors) >= 1
    assert errors[0].row_number == 1


def test_validation_flags_invalid_zip(db_session: Session, clinic, make_admin) -> None:
    job = _upload(db_session, clinic, make_admin, [["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "not-a-zip"]])
    job.column_mapping = _VALID_MAPPING
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)

    row = db_session.query(ImportRow).filter(ImportRow.import_id == job.id).one()
    assert row.classification == RowClassification.INVALID
    assert any("zip" in e["message"].lower() for e in row.errors)


def test_validation_flags_invalid_email(db_session: Session, clinic, make_admin) -> None:
    job = _upload(
        db_session,
        clinic,
        make_admin,
        [["Mary Smith", "", "not-an-email", "123 Main St", "Hoboken", "NJ", "07030"]],
    )
    job.column_mapping = _VALID_MAPPING
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)

    row = db_session.query(ImportRow).filter(ImportRow.import_id == job.id).one()
    assert row.classification == RowClassification.INVALID


def test_validation_flags_malformed_phone(db_session: Session, clinic, make_admin) -> None:
    job = _upload(db_session, clinic, make_admin, [["Mary Smith", "abc", "", "123 Main St", "Hoboken", "NJ", "07030"]])
    job.column_mapping = _VALID_MAPPING
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)

    row = db_session.query(ImportRow).filter(ImportRow.import_id == job.id).one()
    assert row.classification == RowClassification.INVALID


def test_validation_flags_duplicate_rows_within_file(db_session: Session, clinic, make_admin) -> None:
    job = _upload(
        db_session,
        clinic,
        make_admin,
        [
            ["Mary Smith", "", "mary@example.com", "123 Main St", "Hoboken", "NJ", "07030"],
            ["Different Name", "", "mary@example.com", "456 Other St", "Jersey City", "NJ", "07302"],
        ],
    )
    job.column_mapping = _VALID_MAPPING
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)

    rows = {r.row_number: r for r in db_session.query(ImportRow).filter(ImportRow.import_id == job.id).all()}
    assert rows[1].classification == RowClassification.VALID
    assert rows[2].classification == RowClassification.DUPLICATE_EXACT
    assert rows[2].duplicate_of_row_number == 1
    assert rows[2].duplicate_patient_id is None


def test_validation_flags_exact_duplicate_of_existing_patient(db_session: Session, clinic, make_admin) -> None:
    existing = make_patient(db_session, clinic, first_name="Mary", last_name="Smith", email="mary@example.com")
    job = _upload(
        db_session,
        clinic,
        make_admin,
        [["Mary Smith", "", "mary@example.com", "999 New Address", "Newark", "NJ", "07102"]],
    )
    job.column_mapping = _VALID_MAPPING
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)

    row = db_session.query(ImportRow).filter(ImportRow.import_id == job.id).one()
    assert row.classification == RowClassification.DUPLICATE_EXACT
    assert row.duplicate_patient_id == existing.id
    assert row.duplicate_confidence == 100.0


def test_validation_flags_probable_duplicate_of_existing_patient(db_session: Session, clinic, make_admin) -> None:
    # Matches docs/08_Import_System.md's own worked example: "John Smith" vs existing "John A Smith".
    existing = make_patient(db_session, clinic, first_name="John", last_name="A Smith", zip_code="07030")
    job = _upload(db_session, clinic, make_admin, [["John Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"]])
    job.column_mapping = _VALID_MAPPING
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)

    row = db_session.query(ImportRow).filter(ImportRow.import_id == job.id).one()
    assert row.classification == RowClassification.DUPLICATE_PROBABLE
    assert row.duplicate_patient_id == existing.id
    assert 0 < row.duplicate_confidence < 100


def test_validation_does_not_flag_unrelated_existing_patient(db_session: Session, clinic, make_admin) -> None:
    make_patient(db_session, clinic, first_name="Someone", last_name="Else", zip_code="99999")
    job = _upload(db_session, clinic, make_admin, [["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"]])
    job.column_mapping = _VALID_MAPPING
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)

    row = db_session.query(ImportRow).filter(ImportRow.import_id == job.id).one()
    assert row.classification == RowClassification.VALID


def test_validation_does_not_reject_whole_file_for_one_bad_row(db_session: Session, clinic, make_admin) -> None:
    job = _upload(
        db_session,
        clinic,
        make_admin,
        [
            ["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"],
            ["", "", "", "456 Other St", "Jersey City", "NJ", "07302"],  # missing name
            ["John Doe", "", "", "789 Third St", "Newark", "NJ", "07102"],
        ],
    )
    job.column_mapping = _VALID_MAPPING
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)

    db_session.refresh(job)
    assert job.total_records == 3
    assert job.valid_records == 2
    assert job.invalid_records == 1
    assert job.status == ImportStatus.PENDING  # not FAILED - the file as a whole processed fine


def test_re_validation_clears_previous_rows(db_session: Session, clinic, make_admin) -> None:
    """Confirming a corrected mapping and re-running validation shouldn't leave stale rows behind."""
    job = _upload(db_session, clinic, make_admin, [["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"]])
    job.column_mapping = _VALID_MAPPING
    db_session.commit()
    import_service.run_row_validation(db_session, job.id)

    import_service.run_row_validation(db_session, job.id)  # simulate re-running after a mapping change

    rows = db_session.query(ImportRow).filter(ImportRow.import_id == job.id).all()
    assert len(rows) == 1
