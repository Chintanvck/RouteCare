"""
RouteCare AI - Centralized exceptions and error response formatting.

Every error response - whatever raised it - shares one envelope:

    {
      "success": false,
      "error": {"code": "PATIENT_NOT_FOUND", "message": "...", "details": {}},
      "request_id": "..."
    }

Success responses are NOT wrapped in a matching {"success": true, "data": ...}
envelope. Deliberate: this API is already reviewed/tested end-to-end for
Phase 1B with each endpoint returning its resource shape directly
(TokenResponse, UserPublic, ...), and forcing every response through a
generic wrapper fights FastAPI's response_model typing and makes the
OpenAPI/Swagger schema show a useless "data: object" instead of the
real shape. The one thing every response - success or error - does get
is the X-Request-ID header (see app.core.middleware), so correlation
works either way without a body-level wrapper.

Raise the specific subclass that matches the situation; only fall back
to the bare AppError for a one-off status code with no better fit.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging_config import app_logger
from app.core.request_context import get_request_id


class AppError(Exception):
    """Base application error. Prefer a named subclass below where one fits."""

    status_code: int = 500
    default_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message
        self.code = code or self.default_code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "NOT_FOUND"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "FORBIDDEN"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "CONFLICT"


class ValidationError(AppError):
    """For validation failures raised manually in service code, outside Pydantic's own request validation."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "VALIDATION_ERROR"


class BusinessRuleError(AppError):
    """For domain-rule violations that aren't a 404/409/422 in the strict sense (e.g. an expired token)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "BUSINESS_RULE_VIOLATION"


class RateLimitedError(AppError):
    """Too many requests in the current window - see app.core.rate_limiting."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "RATE_LIMITED"


# Note: there is no PayloadTooLargeError class here - app.core.middleware.MaxBodySizeMiddleware
# sends its 413 response directly at the ASGI level instead of raising, since app.add_middleware
# -registered middleware sits *outside* Starlette's own exception-handling middleware and a raised
# exception there would never reach register_exception_handlers below. See that middleware's own
# docstring for the full explanation.


def _error_response(status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body = {
        "success": False,
        "error": {"code": code, "message": message, "details": details or {}},
        "request_id": get_request_id(),
    }
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
            status.HTTP_403_FORBIDDEN: "FORBIDDEN",
            status.HTTP_404_NOT_FOUND: "NOT_FOUND",
            status.HTTP_409_CONFLICT: "CONFLICT",
        }.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _error_response(exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # exc.errors()[i]["ctx"]["error"] can hold the raw exception object
        # (e.g. a custom Pydantic validator's ValueError), which isn't
        # JSON serializable - strip "ctx" before encoding.
        errors = [{k: v for k, v in err.items() if k != "ctx"} for err in exc.errors()]
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "One or more fields failed validation.",
            details={"errors": jsonable_encoder(errors)} if errors else {},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Anything reaching here is a bug or an infra failure (DB error,
        # etc.) we didn't anticipate. Log the full exception server-side;
        # the client only ever sees a generic message - never the
        # exception text, which could leak schema/DSN/stack details.
        app_logger.exception(
            "unhandled_exception",
            extra={"endpoint": request.url.path, "method": request.method},
        )
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An unexpected error occurred.",
        )
