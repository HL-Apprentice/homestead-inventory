"""HTTP API views for Homestead Inventory."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .backup_views import ExportView, ImportView
from .item_views import (
    AllItemsView,
    BarcodeLookupView,
    ConfigView,
    ConsumeView,
    ItemByBarcodeView,
    ItemConsumptionRatesView,
    ItemHistoryView,
    ItemQuantityView,
    ItemsView,
    ItemView,
)
from .media_views import ImageView, UploadView
from .structure_views import (
    CupboardsView,
    OrganizersView,
    RoomsView,
    ShelvesView,
)


def register_views(hass: HomeAssistant) -> None:
    """Instantiate and register every HTTP view (once per HA process).

    Views resolve the repository from hass.data per-request, so they survive
    a config-entry reload without needing to be re-registered.
    """
    views = [
        RoomsView(hass),
        CupboardsView(hass),
        ShelvesView(hass),
        OrganizersView(hass),
        ItemsView(hass),
        ItemByBarcodeView(hass),
        BarcodeLookupView(hass),
        ItemView(hass),
        ItemQuantityView(hass),
        ItemHistoryView(hass),
        ItemConsumptionRatesView(hass),
        AllItemsView(hass),
        ConsumeView(hass),
        ConfigView(hass),
        ExportView(hass),
        ImportView(hass),
        UploadView(hass),
        ImageView(hass),
    ]
    for view in views:
        hass.http.register_view(view)
