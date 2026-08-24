"""RouteCare AI - Import request/response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.import_job import ImportStatus
from app.models.import_row import RowClassification


class ImportUploadResponse(BaseModel):
    id: uuid.UUID
    status: ImportStatus
    file_name: str
    detected_headers: list[str]
    suggested_mapping: dict[str, str]
    total_records: int


class ColumnMappingRequest(BaseModel):
    mapping: dict[str, str] = Field(description="Target Patient field name -> uploaded column header.")


class ImportJobPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    uploaded_by: uuid.UUID
    file_name: str
    source_system: str
    status: ImportStatus
    detected_headers: list[str] | None
    column_mapping: dict[str, Any] | None
    total_records: int | None
    processed_records: int
    valid_records: int | None
    invalid_records: int | None
    duplicate_records: int | None
    new_records: int | None
    successful_records: int | None
    failed_records: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ImportRowPublic(BaseModel):
    row_number: int
    mapped_data: dict[str, Any]
    classification: RowClassification
    errors: list[dict[str, Any]] | None
    duplicate_patient_id: uuid.UUID | None
    duplicate_of_row_number: int | None
    duplicate_confidence: float | None
    imported: bool

    model_config = {"from_attributes": True}


class ImportRowErrorPublic(BaseModel):
    row_number: int
    field_name: str | None
    error_message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConfirmImportRequest(BaseModel):
    include_duplicates: bool = Field(
        default=False, description="If true, duplicate rows are imported as new patients anyway."
    )
