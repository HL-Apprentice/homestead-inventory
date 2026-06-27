"""Service registration + behaviour, booted in real HA."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homestead_inventory.const import DOMAIN


async def _setup(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, unique_id=DOMAIN,
                            title="Homestead Inventory")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _seed_item(hass, qty=5, barcode=None):
    repo = hass.data[DOMAIN]["repository"]
    await repo.create_room("Kitchen")
    await repo.create_cupboard("Kitchen", "Pantry", "")
    await repo.create_shelf("Kitchen", "Pantry", "Top")
    return await repo.create_item(
        "Kitchen", "Pantry", "Top", None,
        {"name": "Rice", "barcode": barcode, "quantity": qty,
         "min_quantity": 1, "track_quantity": True},
    )


async def test_services_registered(hass):
    await _setup(hass)
    for svc in ("consume", "consume_barcode", "set_quantity", "low_stock_to_todo"):
        assert hass.services.has_service(DOMAIN, svc)


async def test_consume_service(hass):
    await _setup(hass)
    item_id = await _seed_item(hass, qty=5)
    await hass.services.async_call(
        DOMAIN, "consume", {"item_id": item_id}, blocking=True
    )
    repo = hass.data[DOMAIN]["repository"]
    hist = await repo.get_item_history(item_id)
    assert len(hist) == 1 and hist[0]["delta"] == -1


async def test_consume_barcode_service(hass):
    await _setup(hass)
    item_id = await _seed_item(hass, qty=4, barcode="555")
    await hass.services.async_call(
        DOMAIN, "consume_barcode", {"barcode": "555"}, blocking=True
    )
    repo = hass.data[DOMAIN]["repository"]
    items = await repo.list_all_items()
    assert items[0]["quantity"] == 3


async def test_consume_barcode_unknown_raises(hass):
    from homeassistant.exceptions import ServiceValidationError

    await _setup(hass)
    await _seed_item(hass, qty=4, barcode="555")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "consume_barcode", {"barcode": "000"}, blocking=True
        )


async def test_set_quantity_service(hass):
    await _setup(hass)
    item_id = await _seed_item(hass, qty=5)
    await hass.services.async_call(
        DOMAIN, "set_quantity", {"item_id": item_id, "quantity": 9}, blocking=True
    )
    repo = hass.data[DOMAIN]["repository"]
    items = await repo.list_all_items()
    assert items[0]["quantity"] == 9


async def test_low_stock_to_todo_service(hass):
    await _setup(hass)
    await _seed_item(hass, qty=1)  # qty 1 <= min 1 -> low stock

    calls = []

    async def _capture(call):
        calls.append(call.data)

    hass.services.async_register("todo", "add_item", _capture)
    await hass.services.async_call(
        DOMAIN, "low_stock_to_todo",
        {"todo_list": "todo.shopping_list"}, blocking=True
    )
    assert len(calls) == 1
    assert "Rice" in calls[0]["item"]
    assert calls[0]["entity_id"] == "todo.shopping_list"


async def test_services_removed_on_unload(hass):
    entry = await _setup(hass)
    assert hass.services.has_service(DOMAIN, "consume")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, "consume")
