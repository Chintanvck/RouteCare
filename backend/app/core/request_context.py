"""
RouteCare AI - Request-scoped correlation context.

Plain contextvars, not a request object passed around explicitly:
this lets deeply nested code (a service function, a log call several
layers down) pick up the current request/user/clinic without every
function signature threading them through. Set once per request by
RequestContextMiddleware (and by get_current_user, once auth resolves),
read anywhere via the getters below - most commonly by the logging
filter in app.core.logging_config.
"""

import contextvars

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)
clinic_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("clinic_id", default=None)


def get_request_id() -> str | None:
    return request_id_var.get()
