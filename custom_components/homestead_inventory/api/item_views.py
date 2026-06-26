"""HTTP views for items, quantity, consume, deep-links and config."""

from __future__ import annotations

import asyncio
import logging

import aiohttp
from aiohttp import web
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import DOMAIN, EVENT_ITEM_CONSUMED, EVENT_LOW_STOCK
from ..storage import images as img
from .base import (
    MAX_ALIASES_LEN,
    MAX_BARCODE_LEN,
    MAX_NAME_LEN,
    HInvView,
    clean_str,
    json_error,
    length_error,
    parse_quantity,
)

# Open Food Facts is a free, public, no-key product database. Only ever called
# when the operator explicitly enables barcode lookup (off by default).
_OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"

_LOGGER = logging.getLogger(__name__)


def _sign_images(view: HInvView, request, items: list[dict]) -> list[dict]:
    token_id = view.token_id(request)
    for it in items:
        it["image"] = img.build_image_url(view.hass, it.get("image", ""), token_id)
    return items


async def _maybe_fire_low_stock(view: HInvView, item_id) -> None:
    payload = await view.repo.low_stock_payload(item_id)
    if payload:
        _LOGGER.debug("Low stock: %s (%s/%s)", payload["name"], payload["quantity"],
                      payload["min_quantity"])
        view.hass.bus.async_fire(EVENT_LOW_STOCK, payload)


# --------------------------------------------------------------------------- #
class ItemsView(HInvView):
    url = f"/api/{DOMAIN}/items"
    name = f"api:{DOMAIN}:items"

    async def get(self, request):
        room = request.query.get("room")
        cupboard = request.query.get("cupboard")
        shelf = request.query.get("shelf")
        organizer = request.query.get("organizer")
        if not room or not cupboard or not shelf:
            return json_error("Missing params")
        items = await self.repo.list_items(room, cupboard, shelf, organizer)
        return web.json_response(_sign_images(self, request, items))

    async def post(self, request):
        data = await request.json()
        room = clean_str(data.get("room"))
        cupboard = clean_str(data.get("cupboard"))
        shelf = clean_str(data.get("shelf"))
        organizer = clean_str(data.get("organizer")) or None
        name = clean_str(data.get("name"))
        if not all([room, cupboard, shelf, name]):
            return json_error("Missing required params")
        if err := (
            length_error(name, MAX_NAME_LEN, "Name")
            or length_error(data.get("aliases"), MAX_ALIASES_LEN, "Aliases")
            or length_error(data.get("barcode"), MAX_BARCODE_LEN, "Barcode")
        ):
            return json_error(err)

        ok_q, quantity = parse_quantity(data.get("quantity"))
        ok_m, min_quantity = parse_quantity(data.get("min_quantity"))
        if not ok_q or not ok_m:
            return json_error("Quantity values must be non-negative integers")

        item = {
            "name": name,
            "aliases": data.get("aliases"),
            "barcode": clean_str(data.get("barcode")) or None,
            "image": data.get("image", "") or "",
            "quantity": quantity,
            "min_quantity": min_quantity,
            "track_quantity": bool(data.get("track_quantity")),
        }
        new_id = await self.repo.create_item(room, cupboard, shelf, organizer, item)
        if new_id is None:
            return json_error("Shelf not found", 404)
        return web.json_response({"id": new_id, "name": name})


class AllItemsView(HInvView):
    url = f"/api/{DOMAIN}/all_items"
    name = f"api:{DOMAIN}:all_items"

    async def get(self, request):
        items = await self.repo.list_all_items()
        return web.json_response(_sign_images(self, request, items))


class ItemView(HInvView):
    url = f"/api/{DOMAIN}/items/{{item_id}}"
    name = f"api:{DOMAIN}:item"

    async def patch(self, request, item_id):
        data = await request.json()

        if err := (
            length_error(data.get("name"), MAX_NAME_LEN, "Name")
            or length_error(data.get("aliases"), MAX_ALIASES_LEN, "Aliases")
            or length_error(data.get("barcode"), MAX_BARCODE_LEN, "Barcode")
        ):
            return json_error(err)

        # Validate any quantities that are present.
        if "quantity" in data:
            ok, val = parse_quantity(data["quantity"])
            if not ok:
                return json_error("Quantity must be a non-negative integer")
            data["quantity"] = val
        if "min_quantity" in data:
            ok, val = parse_quantity(data["min_quantity"])
            if not ok:
                return json_error("Minimum quantity must be a non-negative integer")
            data["min_quantity"] = val

        count, stale, error = await self.repo.update_item(item_id, data)
        if error:
            return json_error(error, 404)
        if count == 0:
            return json_error("Item not found", 404)
        if stale:
            await self.hass.async_add_executor_job(img.delete_image_file, self.hass, stale)
        if "quantity" in data:
            await _maybe_fire_low_stock(self, item_id)
        return web.json_response({"message": "Updated"})

    async def delete(self, request, item_id):
        count, old_image = await self.repo.delete_item(item_id)
        if count == 0:
            return json_error("Item not found", 404)
        if old_image:
            await self.hass.async_add_executor_job(
                img.delete_image_file, self.hass, old_image
            )
        return web.json_response({"message": "Deleted"})


class ItemQuantityView(HInvView):
    url = f"/api/{DOMAIN}/items/{{item_id}}/quantity"
    name = f"api:{DOMAIN}:item_quantity"

    async def patch(self, request, item_id):
        data = await request.json()
        kwargs = {}
        if "quantity" in data:
            ok, val = parse_quantity(data["quantity"])
            if not ok:
                return json_error("Quantity must be a non-negative integer")
            kwargs["quantity"] = val
        if "min_quantity" in data:
            ok, val = parse_quantity(data["min_quantity"])
            if not ok:
                return json_error("Minimum quantity must be a non-negative integer")
            kwargs["min_quantity"] = val
        if "track_quantity" in data:
            kwargs["track_quantity"] = data["track_quantity"]

        count = await self.repo.update_item_quantity(item_id, **kwargs)
        if count == 0:
            return json_error("Item not found", 404)
        await _maybe_fire_low_stock(self, item_id)
        return web.json_response({"message": "Updated"})


class ConsumeView(HInvView):
    url = f"/api/{DOMAIN}/consume/{{item_id}}"
    name = f"api:{DOMAIN}:consume"

    async def post(self, request, item_id):
        result, error = await self.repo.consume_item(item_id)
        if error:
            status = 404 if error == "Item not found" else 400
            return json_error(error, status)

        if result["is_low_stock"] and result["new_quantity"] > 0:
            self.hass.bus.async_fire(
                EVENT_LOW_STOCK,
                {
                    "item_id": result["id"],
                    "name": result["name"],
                    "aliases": result["aliases"],
                    "quantity": result["new_quantity"],
                    "min_quantity": result["min_quantity"],
                    "room": result["room"],
                    "cupboard": result["cupboard"],
                    "shelf": result["shelf"],
                    "location": result["location"],
                },
            )
        self.hass.bus.async_fire(
            EVENT_ITEM_CONSUMED,
            {
                "item_id": result["id"],
                "name": result["name"],
                "old_quantity": result["old_quantity"],
                "new_quantity": result["new_quantity"],
                "location": result["location"],
            },
        )
        return web.json_response(result)


class ItemDeepLinkView(HInvView):
    url = f"/api/{DOMAIN}/items/{{item_id}}/consume_link"
    name = f"api:{DOMAIN}:item_consume_link"

    async def get(self, request, item_id):
        deep_link = f"homeassistant://navigate/{DOMAIN}/consume/{item_id}"
        return web.json_response(
            {
                "deep_link": deep_link,
                "webhook_url": f"{self._base_url()}/api/{DOMAIN}/consume/{item_id}",
                "item_id": item_id,
            }
        )

    def _base_url(self) -> str:
        cfg = self.hass.config
        if getattr(cfg, "external_url", None):
            return cfg.external_url
        if getattr(cfg, "internal_url", None):
            return cfg.internal_url
        return f"http://{cfg.api.local_ip}:8123"


class ConfigView(HInvView):
    url = f"/api/{DOMAIN}/config"
    name = f"api:{DOMAIN}:config"

    async def get(self, request):
        entry = self.hass.data.get(DOMAIN, {}).get("entry")
        allow = True
        language = "en"
        barcode_lookup = False
        if entry is not None:
            allow = entry.options.get("allow_structure_modification", True)
            language = entry.options.get("language", "en")
            barcode_lookup = entry.options.get("enable_barcode_lookup", False)
        return web.json_response(
            {
                "allow_structure_modification": allow,
                "qr_redirect_url": f"homeassistant://navigate/{DOMAIN}" if allow else None,
                "language": language,
                "enable_barcode_lookup": barcode_lookup,
            }
        )


class ItemByBarcodeView(HInvView):
    """Find an item by its stored barcode (scan-to-find)."""

    url = f"/api/{DOMAIN}/by_barcode"
    name = f"api:{DOMAIN}:by_barcode"

    async def get(self, request):
        code = clean_str(request.query.get("code"))
        if not code:
            return json_error("Missing barcode")
        item = await self.repo.find_item_by_barcode(code)
        if item is None:
            return json_error("No item with that barcode", 404)
        item["image"] = img.build_image_url(
            self.hass, item.get("image", ""), self.token_id(request)
        )
        return web.json_response(item)


class BarcodeLookupView(HInvView):
    """Optional product-name lookup from a barcode via Open Food Facts.

    Off by default; only reachable when the operator enables the
    'enable_barcode_lookup' option (the one place this integration makes an
    outbound call). Barcodes are validated as numeric to keep the request safe.
    """

    url = f"/api/{DOMAIN}/barcode_lookup"
    name = f"api:{DOMAIN}:barcode_lookup"

    async def get(self, request):
        entry = self.hass.data.get(DOMAIN, {}).get("entry")
        if not (entry and entry.options.get("enable_barcode_lookup", False)):
            return json_error("Barcode lookup is disabled", 403)

        code = clean_str(request.query.get("code"))
        if not code or not code.isdigit() or len(code) > MAX_BARCODE_LEN:
            return json_error("Invalid barcode")

        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                _OFF_URL.format(code=code),
                params={"fields": "product_name,brands"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return web.json_response({"found": False})
                payload = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return json_error("Lookup service unavailable", 504)

        product = payload.get("product") or {}
        name = (product.get("product_name") or "").strip()
        brand = (product.get("brands") or "").split(",")[0].strip()
        if not name:
            return web.json_response({"found": False})
        full = f"{brand} {name}".strip() if brand else name
        return web.json_response({"found": True, "name": full[:MAX_NAME_LEN]})
