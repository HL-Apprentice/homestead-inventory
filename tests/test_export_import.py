"""Full-inventory export / import (backup & restore)."""


async def _seed(repo):
    await repo.create_room("Kitchen")
    await repo.create_cupboard("Kitchen", "Pantry", "")
    await repo.create_shelf("Kitchen", "Pantry", "Top")
    await repo.create_organizer("Kitchen", "Pantry", "Top", "Bin", "")
    await repo.create_item(
        "Kitchen", "Pantry", "Top", "Bin",
        {"name": "Rice", "aliases": "basmati", "barcode": "111",
         "quantity": 5, "min_quantity": 2, "track_quantity": True},
    )
    await repo.create_item(
        "Kitchen", "Pantry", "Top", None,
        {"name": "Salt", "quantity": 1, "min_quantity": 1, "track_quantity": True},
    )


async def test_export_shape(repo):
    await _seed(repo)
    data = await repo.export_data()
    assert [r["name"] for r in data["rooms"]] == ["Kitchen"]
    assert len(data["cupboards"]) == 1 and data["cupboards"][0]["room"] == "Kitchen"
    assert len(data["shelves"]) == 1
    assert len(data["organizers"]) == 1
    assert len(data["items"]) == 2
    rice = next(i for i in data["items"] if i["name"] == "Rice")
    assert rice["organizer"] == "Bin" and rice["barcode"] == "111"
    assert rice["room"] == "Kitchen" and rice["shelf"] == "Top"


async def test_export_preserves_empty_containers(repo):
    await repo.create_room("Garage")
    await repo.create_cupboard("Garage", "Wall", "")
    await repo.create_shelf("Garage", "Wall", "Hooks")
    data = await repo.export_data()
    assert any(s["name"] == "Hooks" for s in data["shelves"])
    assert data["items"] == []


async def test_import_replace_roundtrip(repo, repo_cls, tmp_path):
    await _seed(repo)
    data = await repo.export_data()

    fresh = repo_cls(str(tmp_path / "fresh.db"))
    await fresh.async_initialize()
    try:
        counts = await fresh.import_data(data, replace=True)
        assert counts["rooms"] == 1 and counts["items"] == 2
        out = await fresh.export_data()
        assert len(out["items"]) == 2
        names = sorted(i["name"] for i in out["items"])
        assert names == ["Rice", "Salt"]
        rice = next(i for i in out["items"] if i["name"] == "Rice")
        assert rice["organizer"] == "Bin" and rice["quantity"] == 5
    finally:
        await fresh.async_close()


async def test_import_merge_is_idempotent(repo):
    await _seed(repo)
    data = await repo.export_data()
    # Re-importing the same data in merge mode must not duplicate anything.
    counts = await repo.import_data(data, replace=False)
    assert counts == {"rooms": 0, "cupboards": 0, "shelves": 0,
                      "organizers": 0, "items": 0}
    out = await repo.export_data()
    assert len(out["items"]) == 2
    assert len(out["rooms"]) == 1


async def test_import_replace_wipes_existing(repo):
    await _seed(repo)
    new_data = {
        "rooms": [{"name": "Office"}],
        "cupboards": [], "shelves": [], "organizers": [],
        "items": [],
    }
    await repo.import_data(new_data, replace=True)
    out = await repo.export_data()
    assert [r["name"] for r in out["rooms"]] == ["Office"]
    assert out["items"] == []


async def test_import_merge_adds_new_to_existing(repo):
    await _seed(repo)
    add = {
        "rooms": [{"name": "Kitchen"}],
        "cupboards": [{"room": "Kitchen", "name": "Pantry", "image": ""}],
        "shelves": [{"room": "Kitchen", "cupboard": "Pantry", "name": "Top"}],
        "organizers": [],
        "items": [{"room": "Kitchen", "cupboard": "Pantry", "shelf": "Top",
                   "organizer": None, "name": "Flour", "quantity": 3,
                   "min_quantity": 1, "track_quantity": True}],
    }
    counts = await repo.import_data(add, replace=False)
    assert counts["items"] == 1 and counts["rooms"] == 0
    out = await repo.export_data()
    assert sorted(i["name"] for i in out["items"]) == ["Flour", "Rice", "Salt"]


async def test_import_ignores_blank_and_bad_rows(repo):
    data = {
        "rooms": [{"name": ""}, {"name": "  "}],
        "cupboards": [],
        "shelves": [],
        "organizers": [],
        "items": [{"name": "Orphan", "room": "Nowhere", "cupboard": "X",
                   "shelf": "Y", "quantity": 1}],
    }
    counts = await repo.import_data(data, replace=False)
    # The orphan item's path is auto-created (room/cupboard/shelf), item added.
    assert counts["items"] == 1
    out = await repo.export_data()
    assert any(i["name"] == "Orphan" for i in out["items"])
    # Blank room names were skipped.
    assert all(r["name"].strip() for r in out["rooms"])
