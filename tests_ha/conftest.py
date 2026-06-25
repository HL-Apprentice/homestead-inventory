"""Fixtures for the full HTTP harness (boots the integration inside HA).

Requires pytest-homeassistant-custom-component. Run with the HA venv:
    ~/.cache/homestead-ha-venv/bin/pytest tests_ha
"""

import pathlib
import sys

import pytest

# Make the repo's `custom_components` package importable by HA's loader.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let HA load our custom integration in tests."""
    yield


@pytest.fixture(autouse=True)
def _reset_http_registration():
    """Each test gets a fresh hass, so reset the process-level registration flag
    so views/static paths register on every test's HTTP app."""
    import custom_components.homestead_inventory as hsi

    hsi._HTTP_REGISTERED = False
    yield


@pytest.fixture(autouse=True)
def _clean_db(hass):
    """PHCC reuses a fixed test config dir, so wipe our data dir before each
    test to guarantee a fresh database (no row accumulation across tests/runs)."""
    import shutil
    from pathlib import Path

    data_dir = Path(hass.config.path("homestead_inventory"))
    if data_dir.exists():
        shutil.rmtree(data_dir, ignore_errors=True)
    yield
