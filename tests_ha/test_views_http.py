"""End-to-end HTTP tests: boot the integration in HA and hit the real API."""

import sqlite3

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homestead_inventory.const import DOMAIN

BASE = f"/api/{DOMAIN}"


async def _setup(hass, require_admin=False, enable_barcode_lookup=False):
    options = {}
    if require_admin:
        options["require_admin"] = True
    if enable_barcode_lookup:
        options["enable_barcode_lookup"] = True
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options=options,
        unique_id=DOMAIN,
        title="Homestead Inventory",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entry_sets_up(hass):
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED


async def test_create_and_list_room(hass, hass_client):
    await _setup(hass)
    client = await hass_client()

    resp = await client.post(f"{BASE}/rooms", json={"name": "Kitchen"})
    assert resp.status == 200
    assert (await resp.json())["name"] == "Kitchen"

    resp = await client.get(f"{BASE}/rooms")
    assert resp.status == 200
    rooms = await resp.json()
    assert any(r["name"] == "Kitchen" for r in rooms)


async def test_name_length_capped(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    resp = await client.post(f"{BASE}/rooms", json={"name": "x" * 101})
    assert resp.status == 400
    assert "100" in (await resp.json())["error"]


async def test_duplicate_room_rejected(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    await client.post(f"{BASE}/rooms", json={"name": "Garage"})
    resp = await client.post(f"{BASE}/rooms", json={"name": "garage"})
    assert resp.status == 400
    assert "exists" in (await resp.json())["error"].lower()


async def test_full_hierarchy_and_item(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    await client.post(f"{BASE}/rooms", json={"name": "Kitchen"})
    await client.post(f"{BASE}/cupboards", json={"room": "Kitchen", "name": "Pantry"})
    await client.post(
        f"{BASE}/shelves", json={"room": "Kitchen", "cupboard": "Pantry", "name": "Top"}
    )
    resp = await client.post(
        f"{BASE}/items",
        json={
            "room": "Kitchen",
            "cupboard": "Pantry",
            "shelf": "Top",
            "name": "Rice",
            "quantity": 1,
            "min_quantity": 2,
            "track_quantity": True,
        },
    )
    assert resp.status == 200

    resp = await client.get(f"{BASE}/all_items")
    items = await resp.json()
    assert len(items) == 1 and items[0]["name"] == "Rice"


async def test_negative_quantity_rejected(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    await client.post(f"{BASE}/rooms", json={"name": "Kitchen"})
    await client.post(f"{BASE}/cupboards", json={"room": "Kitchen", "name": "Pantry"})
    await client.post(
        f"{BASE}/shelves", json={"room": "Kitchen", "cupboard": "Pantry", "name": "Top"}
    )
    resp = await client.post(
        f"{BASE}/items",
        json={
            "room": "Kitchen",
            "cupboard": "Pantry",
            "shelf": "Top",
            "name": "Bad",
            "quantity": -5,
        },
    )
    assert resp.status == 400


async def test_db_error_returns_503(hass, hass_client):
    await _setup(hass)
    repo = hass.data[DOMAIN]["repository"]

    async def boom():
        raise sqlite3.OperationalError("disk I/O error")

    repo.list_rooms = boom  # simulate a storage failure
    client = await hass_client()
    resp = await client.get(f"{BASE}/rooms")
    assert resp.status == 503


async def test_unauthenticated_is_rejected(hass, hass_client_no_auth):
    await _setup(hass)
    client = await hass_client_no_auth()
    resp = await client.get(f"{BASE}/rooms")
    assert resp.status == 401


async def test_admin_gate_allows_admin(hass, hass_client):
    await _setup(hass, require_admin=True)
    client = await hass_client()  # PHCC's default client is an admin user
    resp = await client.post(f"{BASE}/rooms", json={"name": "Kitchen"})
    assert resp.status == 200


async def test_admin_gate_blocks_non_admin(
    hass, hass_client, hass_read_only_access_token
):
    await _setup(hass, require_admin=True)
    client = await hass_client(hass_read_only_access_token)
    resp = await client.get(f"{BASE}/rooms")
    assert resp.status == 403


async def test_non_admin_allowed_when_gate_off(
    hass, hass_client, hass_read_only_access_token
):
    await _setup(hass, require_admin=False)
    client = await hass_client(hass_read_only_access_token)
    resp = await client.get(f"{BASE}/rooms")
    assert resp.status == 200


# --------------------------- barcode (v0.2.0) --------------------------- #
async def _make_shelf(client):
    await client.post(f"{BASE}/rooms", json={"name": "Kitchen"})
    await client.post(f"{BASE}/cupboards", json={"room": "Kitchen", "name": "Pantry"})
    await client.post(
        f"{BASE}/shelves", json={"room": "Kitchen", "cupboard": "Pantry", "name": "Top"}
    )


async def test_create_item_with_barcode_and_find(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    await _make_shelf(client)
    resp = await client.post(
        f"{BASE}/items",
        json={
            "room": "Kitchen",
            "cupboard": "Pantry",
            "shelf": "Top",
            "name": "Rice",
            "barcode": "0123456789012",
        },
    )
    assert resp.status == 200

    resp = await client.get(f"{BASE}/by_barcode?code=0123456789012")
    assert resp.status == 200
    assert (await resp.json())["name"] == "Rice"

    resp = await client.get(f"{BASE}/by_barcode?code=000")
    assert resp.status == 404


async def test_barcode_lookup_disabled_by_default(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    resp = await client.get(f"{BASE}/barcode_lookup?code=0123456789012")
    assert resp.status == 403


async def test_barcode_lookup_enabled(hass, hass_client, aioclient_mock):
    aioclient_mock.get(
        "https://world.openfoodfacts.org/api/v2/product/0123456789012.json",
        params={"fields": "product_name,brands"},
        json={"product": {"product_name": "Basmati Rice", "brands": "ACME, Other"}},
    )
    await _setup(hass, enable_barcode_lookup=True)
    client = await hass_client()
    resp = await client.get(f"{BASE}/barcode_lookup?code=0123456789012")
    assert resp.status == 200
    body = await resp.json()
    assert body["found"] is True and "Rice" in body["name"]


# ---------------------- history + analytics (v0.3.0) ---------------------- #
async def _make_tracked_item(client, qty=5):
    await _make_shelf(client)
    resp = await client.post(
        f"{BASE}/items",
        json={
            "room": "Kitchen",
            "cupboard": "Pantry",
            "shelf": "Top",
            "name": "Rice",
            "quantity": qty,
            "min_quantity": 1,
            "track_quantity": True,
        },
    )
    return (await resp.json())["id"]


async def test_consume_records_history_endpoint(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    item_id = await _make_tracked_item(client, qty=5)

    resp = await client.post(f"{BASE}/consume/{item_id}")
    assert resp.status == 200
    assert (await resp.json())["new_quantity"] == 4

    resp = await client.get(f"{BASE}/items/{item_id}/history")
    assert resp.status == 200
    history = (await resp.json())["history"]
    assert len(history) == 1
    assert history[0]["delta"] == -1 and history[0]["source"] == "consume"


async def test_consumption_rates_endpoint(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    item_id = await _make_tracked_item(client, qty=30)
    for _ in range(3):
        await client.post(f"{BASE}/consume/{item_id}")

    resp = await client.get(f"{BASE}/items/{item_id}/consumption_rates?days=30")
    assert resp.status == 200
    rates = await resp.json()
    assert rates["events"] == 3
    assert rates["total_used"] == 3
    assert rates["current_quantity"] == 27


async def test_history_empty_for_new_item(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    item_id = await _make_tracked_item(client)
    resp = await client.get(f"{BASE}/items/{item_id}/history")
    assert resp.status == 200
    assert (await resp.json())["history"] == []
