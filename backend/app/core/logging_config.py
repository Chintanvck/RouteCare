"""
RouteCare AI - Structured logging.

Every log line is a single JSON object with a fixed base (timestamp,
level, logger, message) plus whatever extra fields the call site or the
ambient request context (RequestContextFilter) attaches - request_id,
user_id, clinic_id, endpoint, method, status, duration_ms, or anything
domain-specific a future module passes via `extra={...}`.

Never pass passwords, JWTs, refresh tokens, reset tokens, or full
request bodies into `extra` - only identifiers and outcomes.

Loggers to use:
- auth_logger      ("routecare.auth")     - auth security events
- access_logger    ("routecare.access")   - one line per HTTP request
- app_logger       ("routecare.app")      - everything else (unhandled errors, etc.)
"""

import json
import logging
from datetime import datetime, timezone

from app.core.request_context import clinic_id_var, request_id_var, user_id_var

auth_logger = logging.getLogger("routecare.auth")
access_logger = logging.getLogger("routecare.access")
app_logger = logging.getLogger("routecare.app")

# Attribute names present on every LogRecord by default. Anything else
# found on a record's __dict__ came from `extra={...}` at the call site
# (or from RequestContextFilter below) and is treated as a structured field.
_STANDARD_RECORD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}


class RequestContextFilter(logging.Filter):
    """Attaches the ambient request_id/user_id/clinic_id to every record that doesn't already carry one."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        if not hasattr(record, "user_id"):
            record.user_id = user_id_var.get()
        if not hasattr(record, "clinic_id"):
            record.clinic_id = clinic_id_var.get()
        return True


class JSONLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS or value is None:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONLogFormatter())
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
