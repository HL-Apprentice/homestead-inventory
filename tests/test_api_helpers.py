"""Unit tests for the HA-independent API helpers (validation + DB guard).

Loaded directly from file (the module imports only aiohttp, no Home Assistant),
so these run without the full HA test harness.
"""

import importlib.util
import pathlib
import sqlite3

import pytest
from aiohttp import web

_HELPERS = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "homestead_inventory"
    / "api"
    / "_helpers.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("hsi_helpers", _HELPERS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


helpers = _load()


# --------------------------- length_error --------------------------- #
def test_length_error_none_and_short_ok():
    assert helpers.length_error(None, 100) is None
    assert helpers.length_error("Kitchen", 100, "Name") is None
    assert helpers.length_error("x" * 100, 100) is None  # exactly at limit


def test_length_error_too_long():
    msg = helpers.length_error("x" * 101, 100, "Name")
    assert msg and "100" in msg and "Name" in msg


# --------------------------- parse_quantity ------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [
        (None, (True, None)),
        (5, (True, 5)),
        ("7", (True, 7)),
        (0, (True, 0)),
        (-1, (False, None)),
        ("abc", (False, None)),
        (1.9, (True, 1)),  # int() truncates a float
    ],
)
def test_parse_quantity(value, expected):
    assert helpers.parse_quantity(value) == expected


# --------------------------- clean_str ------------------------------ #
def test_clean_str():
    assert helpers.clean_str("  hi  ") == "hi"
    assert helpers.clean_str(None) == ""
    assert helpers.clean_str(123) == ""


# --------------------------- guard_db ------------------------------- #
async def test_guard_db_passthrough():
    @helpers.guard_db
    async def handler(self):
        return "ok"

    assert await handler(object()) == "ok"
    assert handler._db_guarded is True


async def test_guard_db_catches_sqlite_error():
    @helpers.guard_db
    async def handler(self):
        raise sqlite3.OperationalError("database or disk is full")

    resp = await handler(object())
    assert isinstance(resp, web.Response)
    assert resp.status == 503


async def test_guard_db_reraises_http_exception():
    @helpers.guard_db
    async def handler(self):
        raise web.HTTPServiceUnavailable()

    with pytest.raises(web.HTTPException):
        await handler(object())


async def test_guard_db_passes_through_value_errors():
    """Non-DB exceptions are not swallowed (only sqlite3.Error is handled)."""

    @helpers.guard_db
    async def handler(self):
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        await handler(object())
