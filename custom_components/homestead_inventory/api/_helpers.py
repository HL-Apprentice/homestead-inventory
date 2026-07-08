"""HA-independent helpers for the HTTP views.

Kept free of any `homeassistant` import so the validation logic and the
database-error guard can be unit-tested without the full Home Assistant test
harness (they only need aiohttp). ``base.py`` re-exports these names.
"""

from __future__ import annotations

import functools
import json
import logging
import sqlite3

from aiohttp import web

_LOGGER = logging.getLogger(__name__)

# Set by HA's auth middleware on every authenticated request.
REFRESH_TOKEN_KEY = "hass_refresh_token_id"

# Length caps for free-text fields (enforced server-side; mirrored in the UI).
MAX_NAME_LEN = 100
MAX_ALIASES_LEN = 255
MAX_BARCODE_LEN = 64


def json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def clean_str(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def length_error(value, max_len: int, label: str = "Value") -> str | None:
    """Return an error message if a string exceeds max_len, else None."""
    if isinstance(value, str) and len(value) > max_len:
        return f"{label} too long (max {max_len} characters)"
    return None


def parse_quantity(value) -> tuple[bool, int | None]:
    """Validate an optional, non-negative integer quantity.

    Returns (ok, value). ``None`` is a valid value (means "unset").
    """
    if value is None:
        return True, None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return False, None
    if n < 0:
        return False, None
    return True, n


def guard_db(handler):
    """Wrap an HTTP handler so an unexpected database error returns a clean 503
    (and is logged server-side) instead of an unhandled 500 with a traceback.

    Validation errors are returned as values (not raised) and pass through;
    HTTPExceptions (e.g. the 503 from a missing repository) re-raise unchanged;
    a malformed/empty request body (``request.json()`` raising JSONDecodeError)
    becomes a clean 400; sqlite3.IntegrityError is handled inside the create/patch
    handlers, so only genuinely unexpected DB errors (disk full, locked,
    corruption) land in the sqlite branch.
    """

    @functools.wraps(handler)
    async def wrapper(self, *args, **kwargs):
        try:
            return await handler(self, *args, **kwargs)
        except web.HTTPException:
            raise
        except json.JSONDecodeError:
            return json_error("Invalid or missing JSON body")
        except sqlite3.Error as err:
            _LOGGER.error(
                "Database error in %s: %s",
                getattr(handler, "__qualname__", handler),
                err,
            )
            return json_error("Storage temporarily unavailable", 503)

    wrapper._db_guarded = True
    return wrapper
