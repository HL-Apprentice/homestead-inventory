"""Regression tests for the security/stability review fixes."""

import sqlite3

import pytest


async def test_reinit_after_close_reopens_cleanly(repo):
    """async_close then a fresh init on the same path works (autocommit reopen)."""
    path = str(repo._db_path)
    await repo.create_room("Garage")
    await repo.async_close()
    await repo.async_initialize()  # re-open same connection lifecycle
    assert len(await repo.list_rooms()) == 1
    assert path  # sanity


async def test_failed_duplicate_does_not_poison_later_writes(repo):
    """A failed INSERT (autocommit) must not leave a dangling transaction that
    corrupts the next successful write."""
    await repo.create_room("Garage")
    with pytest.raises(sqlite3.IntegrityError):
        await repo.create_room("garage")  # UNIQUE NOCASE violation
    # The next write must still commit correctly.
    await repo.create_room("Kitchen")
    names = sorted(r["name"] for r in await repo.list_rooms())
    assert names == ["Garage", "Kitchen"]


async def test_update_item_quantity_sentinel_is_partial(repo):
    """Omitting `quantity` must NOT overwrite it (sentinel, not magic string)."""
    await repo.create_room("Kitchen")
    await repo.create_cupboard("Kitchen", "Pantry", "")
    await repo.create_shelf("Kitchen", "Pantry", "Top")
    item_id = await repo.create_item(
        "Kitchen", "Pantry", "Top", None,
        {"name": "Rice", "quantity": 5, "min_quantity": 2, "track_quantity": True},
    )
    # Update only min_quantity; quantity must remain 5.
    await repo.update_item_quantity(item_id, min_quantity=1)
    tracked = await repo.tracked_items()
    assert tracked[0]["quantity"] == 5
    assert tracked[0]["min_quantity"] == 1


async def test_update_item_quantity_coerces_to_int(repo):
    await repo.create_room("Kitchen")
    await repo.create_cupboard("Kitchen", "Pantry", "")
    await repo.create_shelf("Kitchen", "Pantry", "Top")
    item_id = await repo.create_item(
        "Kitchen", "Pantry", "Top", None,
        {"name": "Rice", "quantity": 1, "min_quantity": 1, "track_quantity": True},
    )
    await repo.update_item_quantity(item_id, quantity="7")  # string from a sloppy caller
    tracked = await repo.tracked_items()
    assert tracked[0]["quantity"] == 7  # stored as int, not "7"


async def test_corrupt_schema_version_raises_and_does_not_leak(repo_cls, repo):
    """A non-integer schema_version must raise a clear error on init, and must
    NOT leave a 'ready' half-open repository."""
    # Corrupt the metadata on the live (autocommit) connection, then close.
    await repo._c().execute(
        "UPDATE metadata SET value = 'garbage' WHERE key = 'schema_version'"
    )
    path = str(repo._db_path)
    await repo.async_close()

    broken = repo_cls(path)
    with pytest.raises(RuntimeError):
        await broken.async_initialize()
    # Must not have left a usable connection behind.
    assert broken._conn is None


async def test_organizer_move_is_atomic_and_carries_items(repo):
    await repo.create_room("Kitchen")
    await repo.create_cupboard("Kitchen", "Pantry", "")
    await repo.create_shelf("Kitchen", "Pantry", "Top")
    await repo.create_shelf("Kitchen", "Pantry", "Bottom")
    await repo.create_organizer("Kitchen", "Pantry", "Top", "Jar", "")
    await repo.create_item(
        "Kitchen", "Pantry", "Top", "Jar",
        {"name": "Salt", "quantity": 1, "track_quantity": False},
    )
    data = await repo.list_organizers("Kitchen", "Pantry", "Top")
    org_id = data["organizers"][0]["id"]
    count, _stale, error = await repo.update_organizer(
        org_id, None, None, ("Kitchen", "Pantry", "Bottom")
    )
    assert error is None and count == 1
    # The item followed the organizer to the new shelf.
    moved = await repo.list_items("Kitchen", "Pantry", "Bottom", "Jar")
    assert len(moved) == 1 and moved[0]["name"] == "Salt"
