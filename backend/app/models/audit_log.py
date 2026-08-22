"""
RouteCare AI - Audit log model.

Per docs/04_Database_Design.md section 16. clinic_id and user_id are
nullable to cover events where the actor isn't fully known yet - e.g. a
failed login attempt against an email address that doesn't exist.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import GUID

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("clinics.id"), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True, index=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
