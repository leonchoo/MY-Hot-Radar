"""
Validation, timestamps, and URL safety for Performance Intelligence.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional


# ISO 8601 with Z or ±HH:MM
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)
# RFC 2822
_RFC2822_RE = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} "
    r"\d{2}:\d{2}:\d{2} (GMT|[+-]\d{4})$"
)

_URL_FORBIDDEN_PREFIXES = (
    "javascript:", "data:", "vbscript:", "file:", "blob:",
)


class ValidationError(ValueError):
    """Raised when a model fails validation."""


def is_valid_url(url: Any) -> bool:
    """A URL is safe iff: string, non-empty, http(s), no whitespace,
    no control chars, < 2048 chars."""
    if not isinstance(url, str) or not url:
        return False
    if any(ch.isspace() for ch in url):
        return False
    if len(url) >= 2048:
        return False
    lower = url.lower()
    for p in _URL_FORBIDDEN_PREFIXES:
        if lower.startswith(p):
            return False
    if not (lower.startswith("http://") or lower.startswith("https://")):
        return False
    for ch in url:
        o = ord(ch)
        if o < 32 or o == 127:
            return False
    return True


def is_metric(value: Any) -> bool:
    """A metric is None (unknown) or a non-negative int. 0 is valid."""
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= 0
    if isinstance(value, float):
        return value.is_integer() and value >= 0
    return False


def parse_timestamp_any(ts: Any) -> Optional[datetime]:
    """Parse ISO 8601 or RFC 2822 → UTC datetime. None on failure."""
    if not isinstance(ts, str) or not ts:
        return None
    if _ISO_RE.match(ts):
        try:
            if ts.endswith("Z"):
                return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
            return datetime.fromisoformat(ts)
        except ValueError:
            return None
    if _RFC2822_RE.match(ts):
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(ts)
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (TypeError, ValueError):
            return None
    return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_str(name: str, value: Any, *,
                 max_len: int = 500, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(
            f"{name} must be a string, got {type(value).__name__}"
        )
    if not allow_empty and not value:
        raise ValidationError(f"{name} must not be empty")
    if len(value) > max_len:
        raise ValidationError(f"{name} too long (>{max_len})")
    for ch in value:
        o = ord(ch)
        if o < 32 and ch not in ("\n", "\t"):
            raise ValidationError(f"{name} contains control characters")
    return value
