"""
RouteCare AI - Import job model.

Per docs/04_Database_Design.md section 13, extended with the fields the
wizard actually needs to function across separate HTTP requests:
`stored_file_path` (private, server-side only - never a public URL),
`detected_headers`/`column_mapping` (JSON, persisted between the upload
and mapping-confirmation steps), and `processed_records` (a live
progress counter, matching docs/05_API_Design.md's GET /imports/{id}
example response shape `{"status": "PROCESSING", ..., "completed": 250}`).

Status is exactly the 5 states requested for Phase 3 - PENDING is
reused for two different waiting points (awaiting column mapping, and
awaiting the user's confirm-to-import decision after validation), which
callers distinguish by whether `total_records` is populated yet. This
avoids inventing extra enum values beyond what was asked for.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import GUID
from app.models.mixins import TimestampMixin

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class ImportStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


class ImportJob(Base, TimestampMixin):
    __tablename__ = "imports"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("clinics.id"), nullable=False, index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="theraoffice")

    status: Mapped[ImportStatus] = mapped_column(
        SAEnum(ImportStatus, name="import_status"), nullable=False, default=ImportStatus.PENDING
    )

    detected_headers: Mapped[list[str] | None] = mapped_column(JSONVariant, nullable=True)
    column_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)

    total_records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invalid_records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_records: Mapped[int | None] = mapped_column(Integer, nullable=True)

    successful_records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_records: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
