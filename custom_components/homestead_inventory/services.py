"""Home Assistant services for Homestead Inventory.

These let automations adjust stock without going through the panel: decrement an
item (by id or barcode), set an exact quantity, or push the current low-stock
list into a to-do list. All resolve the repository from hass.data per-call, so
they keep working across a config-entry reload.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, EVENT_ITEM_CONSUMED, EVENT_LOW_STOCK

_LOGGER = logging.getLogger(__name__)

SERVICE_CONSUME = "consume"
SERVICE_CONSUME_BARCODE = "consume_barcode"
SERVICE_SET_QUANTITY = "set_quantity"
SERVICE_LOW_STOCK_TO_TODO = "low_stock_to_todo"

_CONSUME_SCHEMA = vol.Schema({vol.Required("item_id"): cv.positive_int})
_CONSUME_BARCODE_SCHEMA = vol.Schema(
    {vol.Required("barcode"): vol.All(cv.string, vol.Length(min=1, max=64))}
)
_SET_QUANTITY_SCHEMA = vol.Schema(
    {
        vol.Required("item_id"): cv.positive_int,
        vol.Required("quantity"): cv.positive_int,
    }
)
_LOW_STOCK_TO_TODO_SCHEMA = vol.Schema(
    {vol.Required("todo_list"): cv.entity_id}
)


def _repo(hass: HomeAssistant):
    repo = hass.data.get(DOMAIN, {}).get("repository")
    if repo is None:
        raise HomeAssistantError("Homestead Inventory is not set up")
    return repo


async def _guard_admin(hass: HomeAssistant, call: ServiceCall) -> None:
    """Mirror the HTTP admin gate: when the ``require_admin`` option is on, a
    non-admin USER who calls one of these mutating services is rejected — so the
    gate can't be bypassed via Developer Tools > Services. Calls with no user
    context (automations/scripts, set up by an admin) are trusted and allowed.
    """
    entry = hass.data.get(DOMAIN, {}).get("entry")
    if not (entry and entry.options.get("require_admin", False)):
        return
    user_id = call.context.user_id
    if user_id is None:
        return  # system / automation context
    user = await hass.auth.async_get_user(user_id)
    if user is None or not user.is_admin:
        raise Unauthorized(context=call.context)


def _fire_consume_events(hass: HomeAssistant, result: dict[str, Any]) -> None:
    """Mirror the events the consume HTTP endpoint fires."""
    if result["is_low_stock"] and result["new_quantity"] > 0:
        hass.bus.async_fire(
            EVENT_LOW_STOCK,
            {
                "item_id": result["id"],
                "name": result["name"],
                "aliases": result["aliases"],
                "quantity": result["new_quantity"],
                "min_quantity": result["min_quantity"],
                "room": result["room"],
                "cupboard": result["cupboard"],
                "shelf": result["shelf"],
                "location": result["location"],
            },
        )
    hass.bus.async_fire(
        EVENT_ITEM_CONSUMED,
        {
            "item_id": result["id"],
            "name": result["name"],
            "old_quantity": result["old_quantity"],
            "new_quantity": result["new_quantity"],
            "location": result["location"],
        },
    )


def async_register_services(hass: HomeAssistant) -> None:
    """Register all services (idempotent — safe to call once per process)."""

    async def handle_consume(call: ServiceCall) -> None:
        await _guard_admin(hass, call)
        repo = _repo(hass)
        result, error = await repo.consume_item(call.data["item_id"])
        if error:
            raise ServiceValidationError(error)
        _fire_consume_events(hass, result)

    async def handle_consume_barcode(call: ServiceCall) -> None:
        await _guard_admin(hass, call)
        repo = _repo(hass)
        # Atomic: resolves the barcode and decrements under one lock.
        result, error = await repo.consume_item_by_barcode(call.data["barcode"])
        if error:
            raise ServiceValidationError(error)
        _fire_consume_events(hass, result)

    async def handle_set_quantity(call: ServiceCall) -> None:
        await _guard_admin(hass, call)
        repo = _repo(hass)
        count = await repo.update_item_quantity(
            call.data["item_id"], quantity=call.data["quantity"]
        )
        if count == 0:
            raise ServiceValidationError("Item not found")
        payload = await repo.low_stock_payload(call.data["item_id"])
        if payload:
            hass.bus.async_fire(EVENT_LOW_STOCK, payload)

    async def handle_low_stock_to_todo(call: ServiceCall) -> None:
        await _guard_admin(hass, call)
        repo = _repo(hass)
        items = await repo.low_stock_items()
        todo_list = call.data["todo_list"]
        failures = 0
        for it in items:
            try:
                await hass.services.async_call(
                    "todo",
                    "add_item",
                    {
                        "entity_id": todo_list,
                        "item": f"{it['name']} ({it['location']})",
                    },
                    blocking=True,
                )
            except Exception as err:  # noqa: BLE001 - keep going, report at the end
                failures += 1
                _LOGGER.warning(
                    "Could not add %s to %s: %s", it["name"], todo_list, err
                )
        _LOGGER.debug(
            "Added %d/%d low-stock item(s) to %s",
            len(items) - failures, len(items), todo_list,
        )
        # Only a total failure (e.g. the to-do list doesn't exist) is an error.
        if items and failures == len(items):
            raise ServiceValidationError(
                f"Could not add items to {todo_list}"
            )

    hass.services.async_register(
        DOMAIN, SERVICE_CONSUME, handle_consume, schema=_CONSUME_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CONSUME_BARCODE, handle_consume_barcode,
        schema=_CONSUME_BARCODE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_QUANTITY, handle_set_quantity,
        schema=_SET_QUANTITY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LOW_STOCK_TO_TODO, handle_low_stock_to_todo,
        schema=_LOW_STOCK_TO_TODO_SCHEMA,
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_CONSUME,
        SERVICE_CONSUME_BARCODE,
        SERVICE_SET_QUANTITY,
        SERVICE_LOW_STOCK_TO_TODO,
    ):
        hass.services.async_remove(DOMAIN, service)
