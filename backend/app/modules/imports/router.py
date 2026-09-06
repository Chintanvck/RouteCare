"""
RouteCare AI - Patient import endpoints.

Restricted to CLINIC_ADMIN and OFFICE_SCHEDULER - therapists don't get
bulk patient import per docs/09_Security_Privacy_Compliance.md's role
table, and nothing in this phase's requirements says otherwise.
"""

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_clinic_id, get_current_user
from app.core.exceptions import ValidationError
from app.core.permissions import UserRole, require_role
from app.core.rate_limiting import rate_limit
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.import_job import (
    ColumnMappingRequest,
    ConfirmImportRequest,
    ImportJobPublic,
    ImportRowErrorPublic,
    ImportRowPublic,
    ImportUploadResponse,
)
from app.services import import_service
from app.workers.import_tasks import execute_import_task, validate_import_task

router = APIRouter()

_ALLOWED_ROLES = (UserRole.CLINIC_ADMIN, UserRole.OFFICE_SCHEDULER)

_UPLOAD_CHUNK_BYTES = 1024 * 1024  # 1 MB


async def _read_bounded(file: UploadFile, *, max_bytes: int) -> bytes:
    """Reads `file` in chunks and aborts as soon as `max_bytes` is exceeded, instead of buffering
    an arbitrarily large upload into memory before app.services.file_validation ever gets a chance
    to reject it on size - a client can otherwise stream gigabytes at this endpoint and exhaust
    server memory well before the existing post-hoc size check runs."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            max_mb = max_bytes / (1024 * 1024)
            raise ValidationError(
                f"File is too large. The maximum upload size is {max_mb:.0f} MB.", code="IMPORT_FILE_TOO_LARGE"
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/patients",
    response_model=ImportUploadResponse,
    status_code=201,
    dependencies=[
        Depends(require_role(*_ALLOWED_ROLES)),
        Depends(rate_limit("import_upload", limit=settings.RATE_LIMIT_IMPORT_UPLOAD_MAX, window_seconds=settings.RATE_LIMIT_IMPORT_UPLOAD_WINDOW_SECONDS)),
    ],
)
async def upload_patients_import(
    file: UploadFile = File(...),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportUploadResponse:
    # +1 byte of slack so a file exactly at the limit isn't falsely rejected by the chunked
    # early-abort check, while file_validation.validate_upload still applies the exact bound.
    content = await _read_bounded(file, max_bytes=settings.IMPORT_MAX_FILE_SIZE_BYTES + 1)
    job, suggested_mapping = import_service.upload_import(
        db,
        clinic_id=clinic_id,
        uploaded_by=current_user.id,
        filename=file.filename or "",
        content=content,
        source_system="theraoffice",
    )
    return ImportUploadResponse(
        id=job.id,
        status=job.status,
        file_name=job.file_name,
        detected_headers=job.detected_headers or [],
        suggested_mapping=suggested_mapping,
        total_records=job.total_records or 0,
    )


@router.get(
    "", response_model=PaginatedResponse[ImportJobPublic], dependencies=[Depends(require_role(*_ALLOWED_ROLES))]
)
def list_imports(
    pagination: PaginationParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ImportJobPublic]:
    items, total = import_service.list_imports(db, clinic_id=clinic_id, pagination=pagination)
    jobs = [ImportJobPublic.model_validate(item) for item in items]
    return PaginatedResponse.create(jobs, page=pagination.page, page_size=pagination.page_size, total=total)


@router.get("/{import_id}", response_model=ImportJobPublic, dependencies=[Depends(require_role(*_ALLOWED_ROLES))])
def get_import(
    import_id: uuid.UUID,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> ImportJobPublic:
    job = import_service.get_import(db, clinic_id=clinic_id, import_id=import_id)
    return ImportJobPublic.model_validate(job)


@router.post(
    "/{import_id}/mapping", response_model=ImportJobPublic, dependencies=[Depends(require_role(*_ALLOWED_ROLES))]
)
def confirm_mapping(
    import_id: uuid.UUID,
    payload: ColumnMappingRequest,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> ImportJobPublic:
    job = import_service.confirm_mapping(db, clinic_id=clinic_id, import_id=import_id, mapping=payload.mapping)
    validate_import_task.delay(str(job.id))
    return ImportJobPublic.model_validate(job)


@router.get(
    "/{import_id}/preview",
    response_model=PaginatedResponse[ImportRowPublic],
    dependencies=[Depends(require_role(*_ALLOWED_ROLES))],
)
def get_preview(
    import_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ImportRowPublic]:
    items, total = import_service.get_preview(db, clinic_id=clinic_id, import_id=import_id, pagination=pagination)
    rows = [ImportRowPublic.model_validate(item) for item in items]
    return PaginatedResponse.create(rows, page=pagination.page, page_size=pagination.page_size, total=total)


@router.get(
    "/{import_id}/errors",
    response_model=PaginatedResponse[ImportRowErrorPublic],
    dependencies=[Depends(require_role(*_ALLOWED_ROLES))],
)
def get_errors(
    import_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ImportRowErrorPublic]:
    items, total = import_service.get_row_errors(db, clinic_id=clinic_id, import_id=import_id, pagination=pagination)
    errors = [ImportRowErrorPublic.model_validate(item) for item in items]
    return PaginatedResponse.create(errors, page=pagination.page, page_size=pagination.page_size, total=total)


@router.post(
    "/{import_id}/confirm", response_model=ImportJobPublic, dependencies=[Depends(require_role(*_ALLOWED_ROLES))]
)
def confirm_import(
    import_id: uuid.UUID,
    payload: ConfirmImportRequest,
    clinic_id: uuid.UUID = Depends(get_current_clinic_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportJobPublic:
    job = import_service.confirm_import(db, clinic_id=clinic_id, import_id=import_id, actor_user_id=current_user.id)
    execute_import_task.delay(str(job.id), payload.include_duplicates)
    return ImportJobPublic.model_validate(job)
