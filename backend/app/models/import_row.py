"""
RouteCare AI - Import row model.

Not in docs/04_Database_Design.md, but necessary: the wizard's mapping-
review/preview/duplicate-review steps need to page through every row of
the uploaded file (not just the failing ones import_errors covers), see
its classification, and know exactly which rows are eligible for
import. One row here per spreadsheet row.

`errors` is a denormalized copy of this row's docs/04-compliant
ImportError entries, kept directly on the row so the preview endpoint
can page through hundreds of rows without an extra join/query per
error - ImportError remains the canonical, queryable audit trail.
"""

import uuid
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Numeric
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import GUID

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class RowClassification(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    DUPLICATE_EXACT = "DUPLICATE_EXACT"
    DUPLICATE_PROBABLE = "DUPLICATE_PROBABLE"


class ImportRow(Base):
    __tablename__ = "import_rows"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    import_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("imports.id"), nullable=False, index=True)

    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    mapped_data: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False)
    classification: Mapped[RowClassification] = mapped_column(
        SAEnum(RowClassification, name="import_row_classification"), nullable=False
    )
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONVariant, nullable=True)

    # Duplicate match info - exactly one of these two is set when
    # classification is DUPLICATE_EXACT/DUPLICATE_PROBABLE.
    duplicate_patient_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("patients.id"), nullable=True)
    duplicate_of_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    imported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_patient_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("patients.id"), nullable=True)
