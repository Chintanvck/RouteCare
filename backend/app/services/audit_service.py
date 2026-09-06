"""
RouteCare AI - Shared audit-log writer (Phase 9).

`app.services.auth_service` already had its own tiny private `_log_audit` helper for
authentication events; this module generalizes that same pattern (just `db.add(AuditLog(...))`,
no commit of its own - it always rides along on the caller's existing commit for the write it's
recording) so every other service can record business events too without duplicating the
construction logic.

Deliberately minimal on what gets stored: `old_value`/`new_value` should hold only what's useful
for an audit trail (changed field *names*, non-PII scheduling values like times/dates/status,
counts) - never a full patient record, address, phone number, or other PII per
docs/09_Security_Privacy_Compliance.md section 14's "data minimization" principle applied to our
own audit trail, not just external AI providers. When there's nothing safe/useful to diff, pass
neither and just record that the action happened against `entity_id`.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def record(
    db: Session,
    *,
    clinic_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            clinic_id=clinic_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
        )
    )
