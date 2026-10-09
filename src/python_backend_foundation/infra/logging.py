"""Structured application logging with optional request correlation."""

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime

_APPLICATION_LOGGER = "python_backend_foundation"
_request_id: ContextVar[str | None] = ContextVar("application_request_id", default=None)


def get_request_id() -> str | None:
    """Read the current request identifier, if inside an HTTP request."""
    return _request_id.get()


def set_request_id(value: str) -> Token[str | None]:
    """Set the current request identifier, returning its restoration token."""
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the previous context after a request finishes."""
    _request_id.reset(token)


class JsonFormatter(logging.Formatter):
    """Produce one JSON object per application log record."""

    def format(self, record: logging.LogRecord) -> str:
        content: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = get_request_id()
        if request_id is not None:
            content["requestId"] = request_id

        error_type = getattr(record, "error_type", None)
        if isinstance(error_type, str):
            content["errorType"] = error_type

        stack_frames = getattr(record, "stack_frames", None)
        if isinstance(stack_frames, list):
            content["stackFrames"] = stack_frames

        if record.exc_info:
            content["exception"] = self.formatException(record.exc_info)

        return json.dumps(content, ensure_ascii=False)


def configure_logging(level: str) -> None:
    """Configure application-specific logging once, without replacing server logs."""
    logger = logging.getLogger(_APPLICATION_LOGGER)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

    logger.setLevel(level)
    logger.propagate = False
