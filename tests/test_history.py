"""Consumption history + analytics, and the v2 -> v3 migration."""

import aiosqlite


async def _seed_item(repo, qty=5):
    await repo.create_room("Kitchen")
    await repo.create_cupboard("Kitchen", "Pantry", "")
    await repo.create_shelf("Kitchen", "Pantry", "Top")
    return await repo.create_item(
        "Kitchen", "Pantry", "Top", None,
        {"name": "Rice", "quantity": qty, "min_quantity": 1, "track_quantity": True},
    )


async def test_consume_records_history(repo):
    item_id = await _seed_item(repo, 5)
    result, error = await repo.consume_item(item_id)
    assert error is None and result["new_quantity"] == 4
    hist = await repo.get_item_history(item_id)
    assert len(hist) == 1
    assert hist[0]["delta"] == -1 and hist[0]["source"] == "consume"


async def test_quantity_adjust_records_history(repo):
    item_id = await _seed_item(repo, 5)
    await repo.update_item_quantity(item_id, quantity=3)  # -2
    await repo.update_item_quantity(item_id, quantity=8)  # +5
    hist = await repo.get_item_history(item_id)
    assert sorted(h["delta"] for h in hist) == [-2, 5]


async def test_no_history_when_quantity_unchanged(repo):
    item_id = await _seed_item(repo, 5)
    await repo.update_item_quantity(item_id, min_quantity=2)  # no qty change
    await repo.update_item_quantity(item_id, quantity=5)  # same value
    assert await repo.get_item_history(item_id) == []


async def test_consumption_rates(repo):
    item_id = await _seed_item(repo, 30)
    for _ in range(3):
        await repo.consume_item(item_id)  # 3 consumed
    rates = await repo.get_consumption_rates(item_id, days=30)
    assert rates["events"] == 3
    assert rates["total_used"] == 3
    assert rates["current_quantity"] == 27
    assert rates["daily_rate"] == round(3 / 30, 2)
    assert rates["days_left"] is not None


async def test_consumption_rates_days_capped(repo):
    item_id = await _seed_item(repo, 30)
    await repo.consume_item(item_id)
    # An absurd window is clamped to the 10-year cap (no pathological query).
    rates = await repo.get_consumption_rates(item_id, days=10**12)
    assert rates["window_days"] == 3650
    # And a zero/negative window floors at 1.
    rates = await repo.get_consumption_rates(item_id, days=0)
    assert rates["window_days"] == 1


async def test_history_cascades_on_item_delete(repo):
    item_id = await _seed_item(repo, 5)
    await repo.consume_item(item_id)
    await repo.delete_item(item_id)
    assert await repo.get_item_history(item_id) == []


async def test_migration_v2_to_v3(repo_cls, tmp_path):
    """A v2 DB (no consumption_history) upgrades to v3 without data loss."""
    path = str(tmp_path / "v2.db")
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
            aliases TEXT, barcode TEXT, image TEXT, shelf_id INTEGER NOT NULL,
            organizer_id INTEGER, quantity INTEGER, min_quantity INTEGER,
            track_quantity INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        """
    )
    await conn.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '2')")
    await conn.execute("INSERT INTO rooms (name) VALUES ('Kitchen')")
    await conn.execute("INSERT INTO cupboards (name, room_id) VALUES ('Pantry', 1)")
    await conn.execute("INSERT INTO shelves (name, cupboard_id) VALUES ('Top', 1)")
    await conn.execute(
        "INSERT INTO items (name, shelf_id, quantity, track_quantity) "
        "VALUES ('Rice', 1, 5, 1)"
    )
    await conn.commit()
    await conn.close()

    repo = repo_cls(path)
    await repo.async_initialize()
    try:
        assert await repo.count_items() == 1  # data survived
        assert await repo.get_item_history(1) == []  # new table exists, empty
        result, error = await repo.consume_item(1)  # and is now writable
        assert error is None and result["new_quantity"] == 4
        assert len(await repo.get_item_history(1)) == 1
    finally:
        await repo.async_close()
