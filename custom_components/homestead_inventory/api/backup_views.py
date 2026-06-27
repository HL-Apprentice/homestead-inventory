"""HTTP views for full-inventory export / import (backup & restore)."""

from __future__ import annotations

import json

from aiohttp import web

from ..const import DOMAIN
from .base import HInvView, json_error

# Upper bound on an import payload. Home Assistant already caps request bodies,
# but we enforce our own limit (and read in chunks) so a large or chunked-encoded
# body can never be fully buffered before the check.
MAX_IMPORT_BYTES = 50 * 1024 * 1024  # 50 MB


class ExportView(HInvView):
    """Download the entire inventory as JSON (containers + items)."""

    url = f"/api/{DOMAIN}/export"
    name = f"api:{DOMAIN}:export"

    async def get(self, request):
        data = await self.repo.export_data()
        return web.json_response(data)


class ImportView(HInvView):
    """Restore an inventory from export JSON.

    Body: {"data": <export object>, "replace": <bool>}. replace=true wipes the
    current inventory first (full restore); replace=false merges (existing
    containers/items are reused, not duplicated).
    """

    url = f"/api/{DOMAIN}/import"
    name = f"api:{DOMAIN}:import"

    async def post(self, request):
        if request.content_length and request.content_length > MAX_IMPORT_BYTES:
            return json_error("Import data too large", 413)

        # Read in bounded chunks so an oversized or chunked-encoded body can't be
        # buffered in full before the size check.
        buf = bytearray()
        async for chunk in request.content.iter_chunked(64 * 1024):
            buf.extend(chunk)
            if len(buf) > MAX_IMPORT_BYTES:
                return json_error("Import data too large", 413)

        try:
            body = json.loads(buf.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return json_error("Invalid JSON body")
        if not isinstance(body, dict):
            return json_error("Invalid JSON body")

        data = body.get("data")
        if not isinstance(data, dict):
            return json_error("Missing or invalid 'data' object")
        # Tolerate a missing key, but reject wrong types so a bad payload can't
        # crash the importer mid-transaction.
        for key in ("rooms", "cupboards", "shelves", "organizers", "items"):
            if key in data and not isinstance(data[key], list):
                return json_error(f"'{key}' must be a list")

        replace = bool(body.get("replace", False))
        counts = await self.repo.import_data(data, replace=replace)
        return web.json_response({"imported": counts, "replace": replace})
