"""Homestead Inventory integration.

A home inventory manager with a dedicated sidebar panel (Rooms > Cupboards >
Shelves > Organizers > Items) backed by a hardened, async SQLite store.
"""

from __future__ import annotations

import logging
import os

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import register_views
from .const import DB_PATH, DOMAIN, INTEGRATION_NAME
from .storage import InventoryRepository

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = ["sensor"]

PANEL_ELEMENT = "homestead-inventory-app"
STATIC_URL = f"/{DOMAIN}_static"

# aiohttp routes and static paths cannot be cleanly removed and persist for the
# life of the HA process, so they must be registered exactly once — even across
# config-entry reloads (which re-run async_setup_entry). This module-level flag
# outlives hass.data (which is popped on unload), so a reload won't try to
# re-register and trip aiohttp's "duplicate route" error.
_HTTP_REGISTERED = False


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    global _HTTP_REGISTERED
    _LOGGER.debug("Setting up %s", INTEGRATION_NAME)

    repo = InventoryRepository(hass.config.path(DB_PATH))
    await repo.async_initialize()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["entry"] = entry
    hass.data[DOMAIN]["repository"] = repo

    if not _HTTP_REGISTERED:
        register_views(hass)
        panel_dir = os.path.join(os.path.dirname(__file__), "panel")
        await hass.http.async_register_static_paths(
            [StaticPathConfig(url_path=STATIC_URL, path=panel_dir, cache_headers=False)]
        )
        _HTTP_REGISTERED = True

    try:
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=INTEGRATION_NAME,
            sidebar_icon="mdi:archive",
            frontend_url_path=DOMAIN,
            config={
                "_panel_custom": {
                    "name": PANEL_ELEMENT,
                    "module_url": f"{STATIC_URL}/panel-wrapper.js",
                }
            },
            require_admin=entry.options.get("require_admin", False),
        )
    except ValueError as err:
        if "Overwriting panel" not in str(err):
            raise
        _LOGGER.debug("Panel already registered: %s", err)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info("%s ready", INTEGRATION_NAME)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-load the entry when options change (e.g. require_admin / language)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    try:
        async_remove_panel(hass, DOMAIN)
    except Exception:  # noqa: BLE001 - panel may already be gone
        pass

    data = hass.data.get(DOMAIN, {})
    repo: InventoryRepository | None = data.get("repository")
    if repo is not None:
        await repo.async_close()
    hass.data.pop(DOMAIN, None)
    return True
