"""End-to-end HTTP tests: boot the integration in HA and hit the real API."""

import sqlite3

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homestead_inventory.const import DOMAIN

BASE = f"/api/{DOMAIN}"


async def _setup(hass, require_admin=False):
    options = {"require_admin": True} if require_admin else {}
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
