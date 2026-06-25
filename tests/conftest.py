"""Test fixtures.

The repository module is intentionally self-contained (only aiosqlite +
stdlib), so we load it directly from its file path. That lets the storage
layer be unit-tested without spinning up a full Home Assistant test harness.
"""

import importlib.util
import pathlib

import pytest
import pytest_asyncio

_REPO_FILE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "homestead_inventory"
    / "storage"
    / "repository.py"
)


def _load_repo_module():
    spec = importlib.util.spec_from_file_location("hsi_repository", _REPO_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repo_module = _load_repo_module()
InventoryRepository = repo_module.InventoryRepository


@pytest.fixture
def repo_cls():
    """The repository class, for tests that manage their own lifecycle."""
    return InventoryRepository


@pytest_asyncio.fixture
async def repo(tmp_path):
    repository = InventoryRepository(str(tmp_path / "test.db"))
    await repository.async_initialize()
    yield repository
    await repository.async_close()
