"""
RouteCare AI - Patient import orchestration.

Mirrors patient_service's shape: plain functions taking an explicit
`db: Session`, directly testable without Celery or a real broker. The
two expensive functions (`run_row_validation`, `run_import_execution`)
are exactly what the Celery task wrappers in app.workers.import_tasks
call - the task wrapper only opens a session and dispatches.

Every query is scoped by clinic_id directly (never load-then-check),
matching patient_service's tenant-isolation pattern - a wrong-clinic
import_id 404s exactly like a nonexistent one.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Query, Session

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, NotFoundError, ValidationError
from app.core.logging_config import app_logger
from app.database.pagination import paginate
from app.models.import_job import ImportJob, ImportStatus
from app.models.import_row import ImportRow, RowClassification
from app.models.import_row_error import ImportRowError
from app.models.patient import Patient
from app.schemas.common import PaginationParams
from app.schemas.patient import PatientCreate
from app.services import patient_service
from app.services.column_mapping import split_full_name, suggest_mapping, validate_mapping
from app.services.duplicate_detection import (
    PatientSignature,
    WithinFileDuplicateTracker,
    match_against_existing_patients,
)
from app.services import audit_service
from app.services.excel_parser import parse_workbook
from app.services.file_validation import scan_for_malware, validate_upload

_FRIENDLY_FIELD_NAMES = {
    "first_name": "First name",
    "last_name": "Last name",
    "address_line_1": "Street address",
    "city": "City",
    "state": "State",
    "zip_code": "ZIP code",
    "email": "Email",
    "phone": "Phone",
}


def _not_found() -> NotFoundError:
    return NotFoundError("Import job was not found.", code="IMPORT_NOT_FOUND")


# --- Private storage ---


def _storage_dir(clinic_id: uuid.UUID) -> Path:
    return Path(settings.IMPORT_STORAGE_DIR) / str(clinic_id)


def _store_file(clinic_id: uuid.UUID, import_id: uuid.UUID, extension: str, content: bytes) -> str:
    directory = _storage_dir(clinic_id)
    directory.mkdir(parents=True, exist_ok=True)

    final_path = directory / f"{import_id}{extension}"
    tmp_path = directory / f".tmp-{import_id}{extension}"
    tmp_path.write_bytes(content)
    os.replace(tmp_path, final_path)  # atomic on the same filesystem; no partially-written file survives
    return str(final_path)


def _read_file(stored_file_path: str) -> bytes:
    return Path(stored_file_path).read_bytes()


# --- Upload ---


def upload_import(
    db: Session, *, clinic_id: uuid.UUID, uploaded_by: uuid.UUID, filename: str, content: bytes, source_system: str
) -> tuple[ImportJob, dict[str, str]]:
    validated = validate_upload(filename=filename, content=content)

    if not scan_for_malware(validated.content):
        raise BusinessRuleError("This file failed a security scan and cannot be uploaded.", code="IMPORT_FILE_UNSAFE")

    headers, raw_rows = parse_workbook(validated.content, validated.extension)
    suggestion = suggest_mapping(headers)

    job = ImportJob(
        clinic_id=clinic_id,
        uploaded_by=uploaded_by,
        file_name=filename,
        stored_file_path="",  # set below once we know the row id
        source_system=source_system,
        status=ImportStatus.PENDING,
        detected_headers=headers,
        total_records=len(raw_rows),
    )
    db.add(job)
    db.flush()

    job.stored_file_path = _store_file(clinic_id, job.id, validated.extension, validated.content)
    db.commit()
    db.refresh(job)

    app_logger.info(
        "import_uploaded",
        extra={"import_id": str(job.id), "clinic_id": str(clinic_id), "row_count": len(raw_rows)},
    )
    return job, suggestion.mapping


# --- Read/list ---


def get_import(db: Session, *, clinic_id: uuid.UUID, import_id: uuid.UUID) -> ImportJob:
    job = db.query(ImportJob).filter(ImportJob.id == import_id, ImportJob.clinic_id == clinic_id).first()
    if job is None:
        raise _not_found()
    return job


def list_imports(db: Session, *, clinic_id: uuid.UUID, pagination: PaginationParams) -> tuple[list[ImportJob], int]:
    query: Query = db.query(ImportJob).filter(ImportJob.clinic_id == clinic_id).order_by(ImportJob.created_at.desc())
    return paginate(query, pagination)


def get_preview(
    db: Session, *, clinic_id: uuid.UUID, import_id: uuid.UUID, pagination: PaginationParams
) -> tuple[list[ImportRow], int]:
    get_import(db, clinic_id=clinic_id, import_id=import_id)  # 404s for cross-clinic/unknown ids
    query: Query = db.query(ImportRow).filter(ImportRow.import_id == import_id).order_by(ImportRow.row_number.asc())
    return paginate(query, pagination)


def get_row_errors(
    db: Session, *, clinic_id: uuid.UUID, import_id: uuid.UUID, pagination: PaginationParams
) -> tuple[list[ImportRowError], int]:
    get_import(db, clinic_id=clinic_id, import_id=import_id)
    query: Query = (
        db.query(ImportRowError).filter(ImportRowError.import_id == import_id).order_by(ImportRowError.row_number.asc())
    )
    return paginate(query, pagination)


# --- Column mapping + validation ---


def confirm_mapping(db: Session, *, clinic_id: uuid.UUID, import_id: uuid.UUID, mapping: dict[str, str]) -> ImportJob:
    job = get_import(db, clinic_id=clinic_id, import_id=import_id)

    if job.status == ImportStatus.PROCESSING:
        raise BusinessRuleError("This import is already being processed.", code="IMPORT_ALREADY_PROCESSING")

    problems = validate_mapping(mapping, job.detected_headers or [])
    if problems:
        raise ValidationError(
            "The column mapping is incomplete.", code="IMPORT_MAPPING_INVALID", details={"problems": problems}
        )

    job.column_mapping = mapping
    job.status = ImportStatus.PROCESSING
    job.processed_records = 0
    db.commit()
    db.refresh(job)
    return job


def _build_mapped_data(raw_row: dict, mapping: dict[str, str]) -> dict[str, str | None]:
    mapped: dict[str, str | None] = {}
    for target, header in mapping.items():
        mapped[target] = raw_row.get(header)

    if mapped.get("full_name") and not (mapped.get("first_name") or mapped.get("last_name")):
        first, last = split_full_name(str(mapped["full_name"]))
        mapped["first_name"] = first or None
        mapped["last_name"] = last or None
    mapped.pop("full_name", None)

    return mapped


_PYDANTIC_VALUE_ERROR_PREFIX = "Value error, "


def _friendly_message(field_name: str | None, error_type: str, original_message: str) -> str:
    label = _FRIENDLY_FIELD_NAMES.get(field_name or "", (field_name or "This field").replace("_", " ").title())
    if error_type in ("missing", "string_type", "string_too_short", "value_error.missing"):
        return f"{label} is required."
    if error_type == "value_error" and original_message.startswith(_PYDANTIC_VALUE_ERROR_PREFIX):
        # Our own field validators (app.schemas.patient) already raise a clear, complete
        # message - Pydantic just prefixes it; the field label would be redundant here.
        return original_message[len(_PYDANTIC_VALUE_ERROR_PREFIX) :]
    return f"{label}: {original_message}"


def _validate_row(mapped: dict) -> tuple[PatientCreate | None, list[dict[str, str | None]]]:
    candidate = {k: v for k, v in mapped.items() if k in PatientCreate.model_fields and v not in (None, "")}
    try:
        return PatientCreate.model_validate(candidate), []
    except PydanticValidationError as exc:
        errors = []
        for err in exc.errors():
            field_name = str(err["loc"][0]) if err["loc"] else None
            errors.append({"field": field_name, "message": _friendly_message(field_name, err["type"], err["msg"])})
        return None, errors


def run_row_validation(db: Session, import_id: uuid.UUID) -> None:
    """Called by the Celery task wrapper. Re-reads the stored file, applies the confirmed mapping to
    every row, validates + duplicate-checks each one, and persists an ImportRow per row."""
    job = db.get(ImportJob, import_id)
    if job is None:
        return

    try:
        content = _read_file(job.stored_file_path)
        extension = Path(job.stored_file_path).suffix
        headers, raw_rows = parse_workbook(content, extension)
        mapping = job.column_mapping or {}

        db.query(ImportRow).filter(ImportRow.import_id == import_id).delete()
        db.query(ImportRowError).filter(ImportRowError.import_id == import_id).delete()
        db.commit()

        existing_patients = (
            db.query(Patient).filter(Patient.clinic_id == job.clinic_id, Patient.deleted_at.is_(None)).all()
        )
        existing_signatures = [
            PatientSignature(
                patient_id=p.id,
                first_name=p.first_name,
                last_name=p.last_name,
                email=p.email,
                phone=p.phone,
                zip_code=p.zip_code,
            )
            for p in existing_patients
        ]

        tracker = WithinFileDuplicateTracker()
        valid = invalid = duplicate = new = 0

        for row_number, raw_row in enumerate(raw_rows, start=1):
            mapped = _build_mapped_data(raw_row, mapping)
            _patient_data, errors = _validate_row(mapped)

            within_dupe_of = tracker.check_and_register(
                row_number,
                first_name=str(mapped.get("first_name") or ""),
                last_name=str(mapped.get("last_name") or ""),
                email=mapped.get("email"),
                phone=mapped.get("phone"),
                zip_code=mapped.get("zip_code"),
            )

            duplicate_patient_id = None
            duplicate_of_row_number = None
            duplicate_confidence = None

            if errors:
                classification = RowClassification.INVALID
            elif within_dupe_of is not None:
                classification = RowClassification.DUPLICATE_EXACT
                duplicate_of_row_number = within_dupe_of
            else:
                match = match_against_existing_patients(
                    first_name=str(mapped.get("first_name") or ""),
                    last_name=str(mapped.get("last_name") or ""),
                    email=mapped.get("email"),
                    phone=mapped.get("phone"),
                    zip_code=mapped.get("zip_code"),
                    existing=existing_signatures,
                )
                if match is not None:
                    classification = (
                        RowClassification.DUPLICATE_EXACT
                        if match.kind == "EXACT"
                        else RowClassification.DUPLICATE_PROBABLE
                    )
                    duplicate_patient_id = match.patient_id
                    duplicate_confidence = match.confidence
                else:
                    classification = RowClassification.VALID

            db.add(
                ImportRow(
                    import_id=import_id,
                    row_number=row_number,
                    mapped_data={k: v for k, v in mapped.items()},
                    classification=classification,
                    errors=errors or None,
                    duplicate_patient_id=duplicate_patient_id,
                    duplicate_of_row_number=duplicate_of_row_number,
                    duplicate_confidence=duplicate_confidence,
                )
            )
            for error in errors:
                db.add(
                    ImportRowError(
                        import_id=import_id,
                        row_number=row_number,
                        field_name=error.get("field"),
                        error_message=error["message"],
                    )
                )

            if classification == RowClassification.INVALID:
                invalid += 1
            elif classification in (RowClassification.DUPLICATE_EXACT, RowClassification.DUPLICATE_PROBABLE):
                duplicate += 1
            else:
                valid += 1
                new += 1

            job.processed_records = row_number
            if row_number % 100 == 0:
                db.commit()

        job.total_records = len(raw_rows)
        job.valid_records = valid
        job.invalid_records = invalid
        job.duplicate_records = duplicate
        job.new_records = new
        job.processed_records = len(raw_rows)
        job.status = ImportStatus.PENDING
        db.commit()

        app_logger.info(
            "import_validated",
            extra={"import_id": str(import_id), "total": len(raw_rows), "valid": valid, "invalid": invalid},
        )
    except Exception:
        db.rollback()
        app_logger.exception("import_validation_failed", extra={"import_id": str(import_id)})
        job = db.get(ImportJob, import_id)
        if job is not None:
            job.status = ImportStatus.FAILED
            job.error_message = "Validation failed unexpectedly. Please try uploading the file again."
            db.commit()


# --- Confirm + execute ---


def confirm_import(
    db: Session, *, clinic_id: uuid.UUID, import_id: uuid.UUID, actor_user_id: uuid.UUID | None = None
) -> ImportJob:
    job = get_import(db, clinic_id=clinic_id, import_id=import_id)

    # total_records is set at upload time too (from the initial parse), so it can't distinguish
    # "just uploaded" from "validated" - valid_records is only ever set once run_row_validation
    # has actually completed.
    if job.status != ImportStatus.PENDING or job.column_mapping is None or job.valid_records is None:
        raise BusinessRuleError(
            "This import isn't ready to confirm yet - it must be validated first.", code="IMPORT_NOT_READY"
        )

    job.status = ImportStatus.PROCESSING
    job.processed_records = 0
    audit_service.record(
        db,
        clinic_id=clinic_id,
        user_id=actor_user_id,
        action="IMPORT_CONFIRMED",
        entity_type="IMPORT_JOB",
        entity_id=job.id,
        new_value={"valid_records": job.valid_records},
    )
    db.commit()
    db.refresh(job)
    return job


def run_import_execution(db: Session, import_id: uuid.UUID, *, include_duplicates: bool) -> None:
    """Called by the Celery task wrapper after confirm. Creates a Patient for every eligible,
    not-yet-imported row. One row's failure never aborts the rest - see module docstring."""
    job = db.get(ImportJob, import_id)
    if job is None:
        return

    try:
        eligible = [RowClassification.VALID]
        if include_duplicates:
            eligible += [RowClassification.DUPLICATE_EXACT, RowClassification.DUPLICATE_PROBABLE]

        rows = (
            db.query(ImportRow)
            .filter(
                ImportRow.import_id == import_id, ImportRow.classification.in_(eligible), ImportRow.imported.is_(False)
            )
            .order_by(ImportRow.row_number.asc())
            .all()
        )

        successful = 0
        failed = 0

        for index, row in enumerate(rows, start=1):
            try:
                candidate = {k: v for k, v in row.mapped_data.items() if k in PatientCreate.model_fields}
                patient_data = PatientCreate.model_validate(candidate)
                patient = patient_service.create_patient(
                    db, clinic_id=job.clinic_id, data=patient_data, source_system=f"import:{job.source_system}"
                )
                row.created_patient_id = patient.id
                row.imported = True
                db.commit()
                successful += 1
            except Exception:
                db.rollback()
                app_logger.exception(
                    "import_row_failed", extra={"import_id": str(import_id), "row_number": row.row_number}
                )
                db.add(
                    ImportRowError(
                        import_id=import_id,
                        row_number=row.row_number,
                        field_name=None,
                        error_message="This row could not be imported due to an unexpected error.",
                    )
                )
                db.commit()
                failed += 1

            job.processed_records = index
            db.commit()

        job.successful_records = successful
        job.failed_records = failed
        job.completed_at = datetime.now(timezone.utc)
        job.status = ImportStatus.COMPLETED if failed == 0 else ImportStatus.COMPLETED_WITH_ERRORS
        db.commit()

        app_logger.info(
            "import_completed", extra={"import_id": str(import_id), "successful": successful, "failed": failed}
        )
    except Exception:
        db.rollback()
        app_logger.exception("import_execution_failed", extra={"import_id": str(import_id)})
        job = db.get(ImportJob, import_id)
        if job is not None:
            job.status = ImportStatus.FAILED
            job.error_message = "Import failed unexpectedly. Rows already imported before the failure are unaffected."
            db.commit()
