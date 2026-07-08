"""Shared base for Homestead Inventory HTTP views.

Pure helpers (validation, the DB-error guard) live in ``_helpers`` so they can
be unit-tested without Home Assistant; they are re-exported here for the view
modules that import from ``.base``.
"""

from __future__ import annotations

import functools

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from ..const import DOMAIN
from ..storage import InventoryRepository
from ._helpers import (  # noqa: F401  (re-exported for view modules)
    MAX_ALIASES_LEN,
    MAX_BARCODE_LEN,
    MAX_NAME_LEN,
    REFRESH_TOKEN_KEY,
    clean_str,
    guard_db,
    json_error,
    length_error,
    parse_quantity,
)

# HA auth middleware stores the authenticated user here.
USER_KEY = "hass_user"


def _is_admin(request: web.Request) -> bool:
    user = request.get(USER_KEY)
    return bool(user and getattr(user, "is_admin", False))


def _admin_gate(handler):
    """When the integration's ``require_admin`` option is on, reject non-admin
    callers with 403 before the handler runs. No-op when the option is off."""

    @functools.wraps(handler)
    async def wrapper(self, request, *args, **kwargs):
        if self._admin_required() and not _is_admin(request):
            return json_error("Admin privileges required", 403)
        return await handler(self, request, *args, **kwargs)

    return wrapper


def _structure_gate(handler):
    """Reject structure-mutating verbs (POST/PATCH/DELETE on rooms/cupboards/
    shelves/organizers) when the ``allow_structure_modification`` option is off.
    Previously the option was only respected by the UI, so a direct API call
    could still alter the tree; this enforces it server-side."""

    @functools.wraps(handler)
    async def wrapper(self, request, *args, **kwargs):
        if not self._structure_mod_enabled():
            return json_error("Structure modification is disabled", 403)
        return await handler(self, request, *args, **kwargs)

    return wrapper


def _unconditional_admin(handler):
    """Require an admin regardless of the ``require_admin`` option. Applied to
    genuinely dangerous verbs — destructive deletes, file writes (upload), the
    bulk import/restore, and the outbound barcode lookup — so a non-admin can
    never trigger them even in the default (require_admin off) household setup."""

    @functools.wraps(handler)
    async def wrapper(self, request, *args, **kwargs):
        if not _is_admin(request):
            return json_error("Admin privileges required", 403)
        return await handler(self, request, *args, **kwargs)

    return wrapper


class HInvView(HomeAssistantView):
    """Base view: authenticated; resolves the repository dynamically.

    Views are registered with aiohttp ONCE for the lifetime of the HA process
    (routes can't be cleanly removed), but a config-entry reload swaps the
    repository in hass.data. Looking it up per-request means a reloaded entry
    is always served by the current repository, and requests during the brief
    unload window return 503 instead of touching a closed connection.

    Every verb handler defined on a subclass is auto-wrapped with an admin gate
    (honoring the ``require_admin`` option) and the DB-error guard.
    """

    requires_auth = True

    # Subclasses whose POST/PATCH/DELETE mutate the container tree set this so
    # the ``allow_structure_modification`` option is enforced server-side.
    structure_mutation = False
    # Verbs that always require an admin, independent of the require_admin
    # option (destructive/file-write/outbound operations).
    admin_verbs: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        structure = getattr(cls, "structure_mutation", False)
        admin_verbs = getattr(cls, "admin_verbs", ())
        for verb in ("get", "post", "put", "patch", "delete"):
            handler = cls.__dict__.get(verb)
            if callable(handler) and not getattr(handler, "_hinv_wrapped", False):
                inner = guard_db(handler)
                if structure and verb in ("post", "put", "patch", "delete"):
                    inner = _structure_gate(inner)
                if verb in admin_verbs:
                    inner = _unconditional_admin(inner)
                wrapped = _admin_gate(inner)
                wrapped._hinv_wrapped = True
                setattr(cls, verb, wrapped)

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _admin_required(self) -> bool:
        entry = self.hass.data.get(DOMAIN, {}).get("entry")
        return bool(entry and entry.options.get("require_admin", False))

    def _structure_mod_enabled(self) -> bool:
        entry = self.hass.data.get(DOMAIN, {}).get("entry")
        return not entry or entry.options.get("allow_structure_modification", True)

    @staticmethod
    def is_admin(request: web.Request) -> bool:
        """Whether the authenticated caller is an admin (independent of the
        require_admin option) — used to gate genuinely destructive operations."""
        return _is_admin(request)

    @property
    def repo(self) -> InventoryRepository:
        repo = self.hass.data.get(DOMAIN, {}).get("repository")
        if repo is None:
            raise web.HTTPServiceUnavailable(text="Homestead Inventory not ready")
        return repo

    @staticmethod
    def token_id(request: web.Request) -> str | None:
        """Refresh-token id of the caller, used to sign image URLs."""
        return request.get(REFRESH_TOKEN_KEY)
