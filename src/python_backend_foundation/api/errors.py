"""RFC 9457 HTTP errors, safe validation messages, and exception handling."""

import logging
import re
import traceback
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..infra.logging import get_request_id

logger = logging.getLogger("python_backend_foundation.api.errors")
_ERROR_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
_SAFE_FIELD_SEGMENT = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,99}")

# Keep messages independent of supplied input and internal validator details.
_VALIDATION_MESSAGES = {
    "missing": "Field is required.",
    "extra_forbidden": "Unexpected field.",
    "int_type": "Expected an integer.",
    "int_parsing": "Expected an integer.",
    "float_type": "Expected a number.",
    "float_parsing": "Expected a number.",
    "string_type": "Expected text.",
    "bool_type": "Expected a boolean.",
    "bool_parsing": "Expected a boolean.",
    "date_type": "Expected a valid date.",
    "date_from_datetime_parsing": "Expected a valid date.",
    "datetime_type": "Expected a timestamp with timezone.",
    "datetime_from_date_parsing": "Expected a valid timestamp.",
    "greater_than": "Value is too small.",
    "greater_than_equal": "Value is too small.",
    "less_than": "Value is too large.",
    "less_than_equal": "Value is too large.",
    "string_too_short": "Text is too short.",
    "string_too_long": "Text is too long.",
}


class ApiException(Exception):
    """An expected HTTP-layer failure with a safe public message."""

    def __init__(
        self,
        status_code: int,
        title: str,
        detail: str,
        code: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if not 400 <= status_code <= 599:
            raise ValueError("API errors require a 4xx or 5xx HTTP status.")
        if not _ERROR_CODE_PATTERN.fullmatch(code):
            raise ValueError("API error codes must be namespaced, e.g. 'common.not_found'.")

        super().__init__(detail)
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.code = code
        self.headers = headers


def problem_response(
    status_code: int,
    title: str,
    detail: str,
    *,
    code: str | None = None,
    request_id: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Generate a Problem Details response without an application success wrapper."""
    content: dict[str, object] = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "detail": detail,
    }
    if code is not None:
        content["code"] = code
    if request_id is not None:
        content["requestId"] = request_id
    if errors is not None:
        content["errors"] = errors

    response_headers = dict(headers or {})
    if request_id is not None:
        response_headers["X-Request-ID"] = request_id

    return JSONResponse(
        content=content,
        status_code=status_code,
        headers=response_headers,
        media_type="application/problem+json",
    )


def _request_id_from_request(request: Request) -> str | None:
    value = request.scope.get("state", {}).get("request_id")
    if isinstance(value, str):
        return value
    return get_request_id()


def _http_code(status_code: int) -> str:
    if status_code == 404:
        return "common.not_found"
    if status_code == 405:
        return "common.method_not_allowed"
    if status_code == 401:
        return "common.unauthorized"
    if status_code == 403:
        return "common.forbidden"
    if status_code >= 500:
        return "common.internal_error"
    return "common.http_error"


def _validation_field(location: tuple[Any, ...]) -> str:
    """Return safe client-facing field paths without echoing arbitrary keys."""
    entries = location[1:] if location and location[0] in {"body", "query", "path", "header", "cookie"} else location
    if not entries:
        return "request"

    parts: list[str] = []
    for segment in entries[:10]:
        if isinstance(segment, int) and segment >= 0:
            if parts:
                parts[-1] = f"{parts[-1]}[{segment}]"
            else:
                parts.append(f"[{segment}]")
        elif isinstance(segment, str) and _SAFE_FIELD_SEGMENT.fullmatch(segment):
            parts.append(segment)
        else:
            return "request"
    return ".".join(parts)


def _validation_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for item in exc.errors()[:25]:
        kind = str(item.get("type", "invalid"))
        if not re.fullmatch(r"[a-z][a-z0-9_]*", kind):
            kind = "invalid"
        location = item.get("loc", ())
        issues.append(
            {
                "field": _validation_field(tuple(location)),
                "code": f"common.validation.{kind}",
                "message": _VALIDATION_MESSAGES.get(kind, "Invalid value."),
            }
        )
    return issues


def _log_unexpected(exc: Exception) -> None:
    """Log diagnostic frames and error type without exposing exception arguments."""
    frames = [
        {"file": frame.filename, "line": frame.lineno, "function": frame.name}
        for frame in traceback.extract_tb(exc.__traceback__)
    ]
    logger.error(
        "Unhandled application request failure.",
        extra={"error_type": type(exc).__name__, "stack_frames": frames},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register HTTP exceptions separately from transport-independent business errors."""

    @app.exception_handler(ApiException)
    async def api_error(request: Request, exc: ApiException) -> JSONResponse:
        if exc.status_code >= 500:
            return problem_response(
                exc.status_code,
                "Internal Server Error",
                "An unexpected server error occurred.",
                code="common.internal_error",
                request_id=_request_id_from_request(request),
            )
        return problem_response(
            exc.status_code,
            exc.title,
            exc.detail,
            code=exc.code,
            request_id=_request_id_from_request(request),
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def framework_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        try:
            title = HTTPStatus(exc.status_code).phrase
        except ValueError:
            title = "HTTP Error"

        if exc.status_code >= 500:
            detail = "An unexpected server error occurred."
        elif isinstance(exc.detail, str):
            detail = exc.detail
        else:
            detail = "The request could not be completed."

        return problem_response(
            exc.status_code,
            title,
            detail,
            code=_http_code(exc.status_code),
            request_id=_request_id_from_request(request),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem_response(
            422,
            "Request validation failed",
            "One or more request fields are invalid.",
            code="common.invalid_request",
            request_id=_request_id_from_request(request),
            errors=_validation_errors(exc),
        )

    @app.exception_handler(Exception)
    async def final_fallback(request: Request, exc: Exception) -> JSONResponse:
        # Captures failures outside the inner error boundary, if any.
        _log_unexpected(exc)
        return problem_response(
            500,
            "Internal Server Error",
            "An unexpected server error occurred.",
            code="common.internal_error",
            request_id=_request_id_from_request(request),
        )


class UnhandledErrorMiddleware:
    """Convert uncaught endpoint exceptions before the outer CORS layer responds."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception as exc:
            if response_started:
                raise
            _log_unexpected(exc)
            response = problem_response(
                500,
                "Internal Server Error",
                "An unexpected server error occurred.",
                code="common.internal_error",
                request_id=get_request_id(),
            )
            await response(scope, receive, tracked_send)
