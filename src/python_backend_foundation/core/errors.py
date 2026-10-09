"""HTTP-independent domain errors with stable namespaced codes."""

import re

_ERROR_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")


class DomainError(Exception):
    """An expected business failure, independent of transport and status codes."""

    def __init__(self, code: str, message: str) -> None:
        if not _ERROR_CODE_PATTERN.fullmatch(code):
            raise ValueError("Domain error codes must be namespaced, e.g. 'orders.already_approved'.")

        super().__init__(message)
        self.code = code
