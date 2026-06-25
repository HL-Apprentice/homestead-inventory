"""Unit tests for the SQLite repository — the safety-critical layer."""

import sqlite3

import pytest


async def _seed(repo):
    """Kitchen > Pantry > Top > Spice Rack > Cumin (qty 1, min 2, tracked)."""
    await repo.create_room("Kitchen")
    await repo.create_cupboard("Kitchen", "Pantry", "")
    await repo.create_shelf("Kitchen", "Pantry", "Top")
    await repo.create_organizer("Kitchen", "Pantry", "Top", "Spice Rack", "")
    return await repo.create_item(
        "Kitchen", "Pantry", "Top", "Spice Rack",
        {"name": "Cumin", "quantity": 1, "min_quantity": 2, "track_quantity": True},
    )


async def test_initialize_sets_foreign_keys_on(repo):
    cur = await repo._c().execute("PRAGMA foreign_keys")
    assert (await cur.fetchone())[0] == 1


async def test_create_and_count(repo):
    await _seed(repo)
    assert await repo.count_items() == 1
    rooms = await repo.list_rooms()
    assert rooms[0]["name"] == "Kitchen" and rooms[0]["itemCount"] == 1


async def test_fk_cascade_delete_room(repo):
    """The headline fix: deleting a room cascades to every descendant."""
    await _seed(repo)
    count, _images = await repo.delete_room(1)
    assert count == 1
    assert await repo.count_items() == 0
    assert await repo.list_rooms() == []
    assert await repo.list_cupboards("Kitchen") == []


async def test_fk_cascade_delete_cupboard(repo):
    await _seed(repo)
    cupboards = await repo.list_cupboards("Kitchen")
    count, _ = await repo.delete_cupboard(cupboards[0]["id"])
    assert count == 1
    assert await repo.count_items() == 0


async def test_low_stock_detection(repo):
    item_id = await _seed(repo)
    low = await repo.low_stock_items()
    assert len(low) == 1 and low[0]["name"] == "Cumin"
    payload = await repo.low_stock_payload(item_id)
    assert payload and payload["quantity"] == 1 and payload["min_quantity"] == 2


async def test_consume_decrements_then_blocks_at_zero(repo):
    item_id = await _seed(repo)
    result, error = await repo.consume_item(item_id)
    assert error is None and result["new_quantity"] == 0
    result2, error2 = await repo.consume_item(item_id)
    assert result2 is None and error2 is not None


async def test_update_quantity_clears_low_stock(repo):
    item_id = await _seed(repo)
    await repo.update_item_quantity(item_id, quantity=5)
    tracked = await repo.tracked_items()
    assert tracked[0]["quantity"] == 5 and tracked[0]["is_low"] is False
    assert await repo.low_stock_payload(item_id) is None


async def test_move_item_between_shelves(repo):
    item_id = await _seed(repo)
    await repo.create_cupboard("Kitchen", "Cabinet", "")
    await repo.create_shelf("Kitchen", "Cabinet", "Lower")
    count, _stale, error = await repo.update_item(
        item_id, {"room": "Kitchen", "cupboard": "Cabinet", "shelf": "Lower"}
    )
    assert error is None and count == 1
    moved = await repo.list_items("Kitchen", "Cabinet", "Lower", None)
    assert len(moved) == 1 and moved[0]["name"] == "Cumin"


async def test_move_item_to_missing_shelf_errors(repo):
    item_id = await _seed(repo)
    count, _stale, error = await repo.update_item(
        item_id, {"room": "Kitchen", "cupboard": "Nope", "shelf": "Ghost"}
    )
    assert count == 0 and error == "Destination shelf not found"


async def test_duplicate_room_is_rejected_case_insensitively(repo):
    await repo.create_room("Garage")
    with pytest.raises(sqlite3.IntegrityError):
        await repo.create_room("garage")


async def test_negative_quantity_is_not_enforced_here(repo):
    """Repository stores what it's given; API layer rejects negatives.

    This documents the boundary: validation lives in the HTTP layer, so the
    repository accepts a negative if called directly.
    """
    item_id = await _seed(repo)
    await repo.update_item_quantity(item_id, quantity=0)
    assert (await repo.low_stock_items())[0]["quantity"] == 0


async def test_organizer_delete_removes_its_items(repo):
    await _seed(repo)
    data = await repo.list_organizers("Kitchen", "Pantry", "Top")
    org_id = data["organizers"][0]["id"]
    deleted, _img, _imgs, items_deleted = await repo.delete_organizer(org_id)
    assert deleted is True and items_deleted == 1
    assert await repo.count_items() == 0
