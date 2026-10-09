"""Small, timezone-safe helpers."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current instant as an aware UTC datetime."""
    return datetime.now(UTC)
