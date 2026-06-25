"""Sensors: total items, low stock, tracked items."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, INTEGRATION_NAME
from .storage import InventoryRepository

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=1)

# Cap the item list carried in state attributes so a large inventory can't
# bloat the recorder DB / exceed HA's state-attribute size limits. The numeric
# state (the count) is always exact; consumers needing the full list should
# query the API. Recommend excluding these sensors from recorder (see README).
MAX_ATTR_ITEMS = 200


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    repo: InventoryRepository = hass.data[DOMAIN]["repository"]
    async_add_entities(
        [
            TotalItemsSensor(repo),
            LowStockSensor(repo),
            TrackedItemsSensor(repo),
        ],
        True,
    )


class _BaseSensor(SensorEntity):
    _attr_native_unit_of_measurement = "items"

    def __init__(self, repo: InventoryRepository) -> None:
        self._repo = repo
        self._attr_native_value = 0


class TotalItemsSensor(_BaseSensor):
    _attr_icon = "mdi:package-variant"

    def __init__(self, repo):
        super().__init__(repo)
        self._attr_name = f"{INTEGRATION_NAME} Total items"
        self._attr_unique_id = f"{DOMAIN}_total_items"

    async def async_update(self) -> None:
        self._attr_native_value = await self._repo.count_items()


class LowStockSensor(_BaseSensor):
    _attr_icon = "mdi:alert-circle"

    def __init__(self, repo):
        super().__init__(repo)
        self._attr_name = f"{INTEGRATION_NAME} Low stock"
        self._attr_unique_id = f"{DOMAIN}_low_stock"
        self._items: list[dict] = []

    @property
    def extra_state_attributes(self):
        attrs = {"items": self._items[:MAX_ATTR_ITEMS]}
        if len(self._items) > MAX_ATTR_ITEMS:
            attrs["items_truncated"] = True
        return attrs

    async def async_update(self) -> None:
        self._items = await self._repo.low_stock_items()
        self._attr_native_value = len(self._items)


class TrackedItemsSensor(_BaseSensor):
    _attr_icon = "mdi:playlist-check"

    def __init__(self, repo):
        super().__init__(repo)
        self._attr_name = f"{INTEGRATION_NAME} Tracked items"
        self._attr_unique_id = f"{DOMAIN}_tracked_items"
        self._items: list[dict] = []

    @property
    def extra_state_attributes(self):
        attrs = {"items": self._items[:MAX_ATTR_ITEMS]}
        if len(self._items) > MAX_ATTR_ITEMS:
            attrs["items_truncated"] = True
        return attrs

    async def async_update(self) -> None:
        self._items = await self._repo.tracked_items()
        self._attr_native_value = len(self._items)
