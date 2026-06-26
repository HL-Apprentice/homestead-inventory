"""Barcode storage + the v1 -> v2 schema migration."""

import aiosqlite


async def _seed_location(repo):
    await repo.create_room("Kitchen")
    await repo.create_cupboard("Kitchen", "Pantry", "")
    await repo.create_shelf("Kitchen", "Pantry", "Top")


async def test_create_and_find_by_barcode(repo):
    await _seed_location(repo)
    item_id = await repo.create_item(
        "Kitchen", "Pantry", "Top", None,
        {"name": "Rice", "barcode": "0123456789012", "track_quantity": False},
    )
    found = await repo.find_item_by_barcode("0123456789012")
    assert found is not None and found["id"] == item_id and found["name"] == "Rice"
    assert found["barcode"] == "0123456789012"
    assert await repo.find_item_by_barcode("nope") is None


async def test_update_barcode(repo):
    await _seed_location(repo)
    item_id = await repo.create_item(
        "Kitchen", "Pantry", "Top", None, {"name": "Beans", "track_quantity": False}
    )
    assert await repo.find_item_by_barcode("555") is None
    count, _stale, error = await repo.update_item(item_id, {"barcode": "555"})
    assert error is None and count == 1
    found = await repo.find_item_by_barcode("555")
    assert found and found["id"] == item_id


async def test_barcode_in_listings(repo):
    await _seed_location(repo)
    await repo.create_item(
        "Kitchen", "Pantry", "Top", None,
        {"name": "Salt", "barcode": "777", "track_quantity": False},
    )
    items = await repo.list_all_items()
    assert items[0]["barcode"] == "777"


async def test_migration_v1_to_v2_preserves_data_and_adds_barcode(repo_cls, tmp_path):
    """A v1 DB (no barcode column) must upgrade in place without data loss."""
    path = str(tmp_path / "v1.db")
    conn = await aiosqlite.connect(path)
    await conn.executescript(
        """
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE rooms (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL
            COLLATE NOCASE UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE cupboards (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
            image TEXT, room_id INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP);
        CREATE TABLE shelves (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
            cupboard_id INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP);
        CREATE TABLE organizers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
            image TEXT, shelf_id INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP);
        CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            aliases TEXT, image TEXT, shelf_id INTEGER NOT NULL, organizer_id INTEGER,
            quantity INTEGER, min_quantity INTEGER,
            track_quantity INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        """
    )
    await conn.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '1')")
    await conn.execute("INSERT INTO rooms (name) VALUES ('Kitchen')")
    await conn.execute("INSERT INTO cupboards (name, room_id) VALUES ('Pantry', 1)")
    await conn.execute("INSERT INTO shelves (name, cupboard_id) VALUES ('Top', 1)")
    await conn.execute("INSERT INTO items (name, shelf_id) VALUES ('Rice', 1)")
    await conn.commit()
    await conn.close()

    repo = repo_cls(path)
    await repo.async_initialize()
    try:
        assert await repo.count_items() == 1  # data survived the migration
        items = await repo.list_all_items()
        assert items[0]["name"] == "Rice"
        assert items[0]["barcode"] is None  # column added, empty
        # And the new column is usable.
        await repo.update_item(items[0]["id"], {"barcode": "999"})
        found = await repo.find_item_by_barcode("999")
        assert found and found["name"] == "Rice"
    finally:
        await repo.async_close()
