"""
Tests for app.services.import_service.run_import_execution, called
directly against the test's SQLite session (same reasoning as
test_imports_validation.py).
"""

from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models.import_job import ImportJob, ImportStatus
from app.models.import_row import ImportRow
from app.models.import_row_error import ImportRowError
from app.models.patient import Patient
from app.services import import_service
from tests.conftest import build_theraoffice_xlsx

_VALID_MAPPING = {
    "full_name": "Patient Full Name",
    "phone": "Phone",
    "email": "Email",
    "address_line_1": "Address",
    "city": "City",
    "state": "State",
    "zip_code": "ZIP",
}


def _validated_job(db_session: Session, clinic, admin, rows: list[list]) -> ImportJob:
    content = build_theraoffice_xlsx(rows)
    job, _mapping = import_service.upload_import(
        db_session,
        clinic_id=clinic.id,
        uploaded_by=admin.id,
        filename="patients.xlsx",
        content=content,
        source_system="theraoffice",
    )
    job.column_mapping = _VALID_MAPPING
    db_session.commit()
    import_service.run_row_validation(db_session, job.id)
    db_session.refresh(job)
    return job


def test_execution_imports_valid_rows_as_patients(db_session: Session, clinic, make_admin) -> None:
    job = _validated_job(
        db_session, clinic, make_admin, [["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"]]
    )
    job.status = ImportStatus.PROCESSING
    db_session.commit()

    import_service.run_import_execution(db_session, job.id, include_duplicates=False)

    patients = db_session.query(Patient).filter(Patient.clinic_id == clinic.id).all()
    assert len(patients) == 1
    assert patients[0].first_name == "Mary"
    assert patients[0].source_system == "import:theraoffice"

    row = db_session.query(ImportRow).filter(ImportRow.import_id == job.id).one()
    assert row.imported is True
    assert row.created_patient_id == patients[0].id

    db_session.refresh(job)
    assert job.status == ImportStatus.COMPLETED
    assert job.successful_records == 1
    assert job.failed_records == 0
    assert job.completed_at is not None


def test_execution_skips_duplicates_by_default(db_session: Session, clinic, make_admin) -> None:
    from tests.conftest import make_patient

    make_patient(db_session, clinic, first_name="Mary", last_name="Smith", email="mary@example.com")
    job = _validated_job(
        db_session,
        clinic,
        make_admin,
        [["Mary Smith", "", "mary@example.com", "999 New Addr", "Newark", "NJ", "07102"]],
    )
    job.status = ImportStatus.PROCESSING
    db_session.commit()

    import_service.run_import_execution(db_session, job.id, include_duplicates=False)

    patients = db_session.query(Patient).filter(Patient.clinic_id == clinic.id).all()
    assert len(patients) == 1  # only the pre-existing one - the duplicate row was not imported

    db_session.refresh(job)
    assert job.successful_records == 0
    assert job.status == ImportStatus.COMPLETED  # nothing eligible failed either


def test_execution_imports_duplicates_when_explicitly_included(db_session: Session, clinic, make_admin) -> None:
    from tests.conftest import make_patient

    make_patient(db_session, clinic, first_name="Mary", last_name="Smith", email="mary@example.com")
    job = _validated_job(
        db_session,
        clinic,
        make_admin,
        [["Mary Smith", "", "mary@example.com", "999 New Addr", "Newark", "NJ", "07102"]],
    )
    job.status = ImportStatus.PROCESSING
    db_session.commit()

    import_service.run_import_execution(db_session, job.id, include_duplicates=True)

    patients = db_session.query(Patient).filter(Patient.clinic_id == clinic.id).all()
    assert len(patients) == 2  # original + the duplicate, imported as a new record
    assert db_session.get(ImportJob, job.id).successful_records == 1


def test_execution_never_touches_existing_patient_record(db_session: Session, clinic, make_admin) -> None:
    """The import must never overwrite/modify an existing patient - even when the duplicate
    row is explicitly imported anyway, the existing record's own fields are untouched."""
    from tests.conftest import make_patient

    existing = make_patient(
        db_session, clinic, first_name="Mary", last_name="Smith", email="mary@example.com", phone="201-000-0000"
    )
    original_phone = existing.phone
    job = _validated_job(
        db_session,
        clinic,
        make_admin,
        [["Mary Smith", "999-999-9999", "mary@example.com", "999 New Addr", "Newark", "NJ", "07102"]],
    )
    job.status = ImportStatus.PROCESSING
    db_session.commit()

    import_service.run_import_execution(db_session, job.id, include_duplicates=True)

    db_session.refresh(existing)
    assert existing.phone == original_phone


def test_excluded_invalid_rows_are_never_imported(db_session: Session, clinic, make_admin) -> None:
    job = _validated_job(
        db_session, clinic, make_admin, [["", "", "", "123 Main St", "Hoboken", "NJ", "07030"]]  # missing name
    )
    job.status = ImportStatus.PROCESSING
    db_session.commit()

    import_service.run_import_execution(db_session, job.id, include_duplicates=True)

    assert db_session.query(Patient).filter(Patient.clinic_id == clinic.id).count() == 0
    db_session.refresh(job)
    assert job.successful_records == 0
    assert job.failed_records == 0


def test_one_row_failure_does_not_abort_the_batch(db_session: Session, clinic, make_admin) -> None:
    job = _validated_job(
        db_session,
        clinic,
        make_admin,
        [
            ["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"],
            ["John Doe", "", "", "456 Other St", "Jersey City", "NJ", "07302"],
        ],
    )
    job.status = ImportStatus.PROCESSING
    db_session.commit()

    real_create_patient = import_service.patient_service.create_patient
    call_count = {"n": 0}

    def flaky_create_patient(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated unexpected DB error")
        return real_create_patient(*args, **kwargs)

    with patch.object(import_service.patient_service, "create_patient", side_effect=flaky_create_patient):
        import_service.run_import_execution(db_session, job.id, include_duplicates=False)

    db_session.refresh(job)
    assert job.successful_records == 1
    assert job.failed_records == 1
    assert job.status == ImportStatus.COMPLETED_WITH_ERRORS

    errors = db_session.query(ImportRowError).filter(ImportRowError.import_id == job.id).all()
    assert any("could not be imported" in e.error_message.lower() for e in errors)

    # The second row succeeded despite the first one failing.
    assert db_session.query(Patient).filter(Patient.clinic_id == clinic.id).count() == 1


def test_confirm_import_rejects_job_not_yet_validated(db_session: Session, clinic, make_admin) -> None:
    import pytest

    from app.core.exceptions import AppError

    content = build_theraoffice_xlsx([["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"]])
    job, _mapping = import_service.upload_import(
        db_session,
        clinic_id=clinic.id,
        uploaded_by=make_admin.id,
        filename="patients.xlsx",
        content=content,
        source_system="theraoffice",
    )

    with pytest.raises(AppError) as exc_info:
        import_service.confirm_import(db_session, clinic_id=clinic.id, import_id=job.id)
    assert exc_info.value.code == "IMPORT_NOT_READY"
