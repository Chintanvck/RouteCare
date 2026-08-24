"""
Tests for temporary file handling: the permanent audit copy is kept
(docs/08_Import_System.md 2.1: "the uploaded file should be stored as
an original copy"), but no stray temporary file survives the write.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.import_job import ImportJob
from app.services import import_service
from tests.conftest import build_theraoffice_xlsx

VALID_ROWS = [["Mary Smith", "", "", "123 Main St", "Hoboken", "NJ", "07030"]]


def test_no_tmp_file_survives_a_successful_upload(db_session: Session, clinic, make_admin) -> None:
    content = build_theraoffice_xlsx(VALID_ROWS)

    job, _mapping = import_service.upload_import(
        db_session,
        clinic_id=clinic.id,
        uploaded_by=make_admin.id,
        filename="patients.xlsx",
        content=content,
        source_system="theraoffice",
    )

    storage_dir = Path(settings.IMPORT_STORAGE_DIR) / str(clinic.id)
    remaining_files = list(storage_dir.iterdir())

    assert Path(job.stored_file_path) in remaining_files
    assert not any(f.name.startswith(".tmp-") for f in remaining_files), "a temp file was left behind"


def test_original_file_is_retained_after_import_completes(db_session: Session, clinic, make_admin) -> None:
    """Per docs/08_Import_System.md 2.1 - the original upload is an audit copy, not a scratch file,
    and must still exist after the whole pipeline (validate + confirm) has run."""
    content = build_theraoffice_xlsx(VALID_ROWS)
    job, _mapping = import_service.upload_import(
        db_session,
        clinic_id=clinic.id,
        uploaded_by=make_admin.id,
        filename="patients.xlsx",
        content=content,
        source_system="theraoffice",
    )
    job.column_mapping = {
        "full_name": "Patient Full Name",
        "address_line_1": "Address",
        "city": "City",
        "state": "State",
        "zip_code": "ZIP",
    }
    db_session.commit()

    import_service.run_row_validation(db_session, job.id)
    import_service.confirm_import(db_session, clinic_id=clinic.id, import_id=job.id)
    import_service.run_import_execution(db_session, job.id, include_duplicates=False)

    assert Path(job.stored_file_path).exists()
    assert Path(job.stored_file_path).read_bytes() == content


def test_uploads_from_different_clinics_are_stored_in_separate_directories(
    db_session: Session, clinic, make_admin
) -> None:
    from app.models.clinic import Clinic

    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()

    content = build_theraoffice_xlsx(VALID_ROWS)
    job_a, _ = import_service.upload_import(
        db_session,
        clinic_id=clinic.id,
        uploaded_by=make_admin.id,
        filename="a.xlsx",
        content=content,
        source_system="theraoffice",
    )
    job_b, _ = import_service.upload_import(
        db_session,
        clinic_id=other_clinic.id,
        uploaded_by=make_admin.id,
        filename="b.xlsx",
        content=content,
        source_system="theraoffice",
    )

    assert Path(job_a.stored_file_path).parent != Path(job_b.stored_file_path).parent
    assert str(clinic.id) in job_a.stored_file_path
    assert str(other_clinic.id) in job_b.stored_file_path


def test_rejected_upload_never_writes_to_disk(db_session: Session, clinic, make_admin) -> None:
    """File type/size/signature checks happen before anything touches disk - a rejected upload
    leaves the storage directory untouched (it may not even exist yet)."""
    from app.core.exceptions import AppError

    storage_dir = Path(settings.IMPORT_STORAGE_DIR) / str(clinic.id)

    try:
        import_service.upload_import(
            db_session,
            clinic_id=clinic.id,
            uploaded_by=make_admin.id,
            filename="patients.csv",
            content=b"not excel",
            source_system="theraoffice",
        )
        raised = False
    except AppError:
        raised = True

    assert raised
    assert not storage_dir.exists() or list(storage_dir.iterdir()) == []
    assert db_session.query(ImportJob).count() == 0
