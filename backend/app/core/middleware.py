"""
RouteCare AI - ASGI middleware.

Plain ASGI classes (not Starlette's BaseHTTPMiddleware) are used here on
purpose. BaseHTTPMiddleware can run the wrapped app in a separate anyio
task depending on Starlette version, which breaks the "set a contextvar
deep inside the route, read it back in the middleware after call_next"
pattern RequestContextMiddleware relies on (contextvars only propagate
forward into a spawned task, not back out of one). A plain ASGI
middleware awaits the inner app directly in the same coroutine, so
context set by get_current_user() is reliably visible in the access-log
line emitted after the response.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

from app.core.logging_config import access_logger
from app.core.request_context import clinic_id_var, request_id_var, user_id_var

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_MAX_REQUEST_ID_LENGTH = 128


def _is_safe_request_id(value: str) -> bool:
    """Client-supplied request IDs are only trusted if they're short and use a safe charset - anything else
    is replaced rather than echoed back or written into logs, to avoid header/log injection or abuse."""
    return 0 < len(value) <= _MAX_REQUEST_ID_LENGTH and all(c.isalnum() or c in "-_" for c in value)


def _header_value(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


class RequestContextMiddleware:
    """Resolves/generates X-Request-ID, exposes it (+ user/clinic once auth resolves) via contextvars,
    echoes it back as a response header, and logs one structured line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header_value(scope, b"x-request-id")
        request_id = incoming if incoming and _is_safe_request_id(incoming) else uuid.uuid4().hex

        rid_token = request_id_var.set(request_id)
        uid_token = user_id_var.set(None)
        cid_token = clinic_id_var.set(None)

        status_holder = {"code": 500}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            access_logger.info(
                "request_completed",
                extra={
                    "method": scope.get("method"),
                    "endpoint": scope.get("path"),
                    "status": status_holder["code"],
                    "duration_ms": round(duration_ms, 2),
                },
            )
            request_id_var.reset(rid_token)
            user_id_var.reset(uid_token)
            clinic_id_var.reset(cid_token)


class SecurityHeadersMiddleware:
    """
    Baseline security headers for a JSON API. Deliberately NOT included:

    - Strict-Transport-Security: belongs at the TLS-terminating edge
      (load balancer/reverse proxy), where whoever owns the certificate
      also controls whether HTTPS is actually enforced. Setting it here
      risks announcing a guarantee the app itself can't back up.
    - Content-Security-Policy: meaningful for HTML/JS responses; this
      API only ever returns JSON, so a CSP would add complexity with no
      real attack surface reduction.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"referrer-policy", b"no-referrer"))
            await send(message)

        await self.app(scope, receive, send_wrapper)
