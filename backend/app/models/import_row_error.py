"""
RouteCare AI - Import row error model.

Per docs/04_Database_Design.md section 14's `import_errors` table
(the class here is named ImportRowError, not ImportError, since
ImportError is a Python builtin exception - shadowing it would be a
footgun for any code in this module or its callers that means the
real thing).

Populated for every field-level validation problem found during the
validation pass, and for any unexpected per-row failure during the
actual import-write pass (distinguished by which phase created them,
not by a separate column - a failed-at-import-time row keeps its
INVALID/VALID classification from validation and simply gets one more
ImportRowError row appended).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import GUID


class ImportRowError(Base):
    __tablename__ = "import_errors"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    import_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("imports.id"), nullable=False, index=True)

    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str] = mapped_column(Text(), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
