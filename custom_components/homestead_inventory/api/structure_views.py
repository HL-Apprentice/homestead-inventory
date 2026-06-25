"""HTTP views for the structure tree: rooms, cupboards, shelves, organizers."""

from __future__ import annotations

import logging
import sqlite3

from aiohttp import web

from ..const import DOMAIN
from ..storage import images as img
from .base import MAX_NAME_LEN, HInvView, clean_str, json_error, length_error

_LOGGER = logging.getLogger(__name__)


async def _delete_images(hass, refs) -> None:
    for ref in refs:
        await hass.async_add_executor_job(img.delete_image_file, hass, ref)


# --------------------------------------------------------------------------- #
# Rooms
# --------------------------------------------------------------------------- #
class RoomsView(HInvView):
    url = f"/api/{DOMAIN}/rooms"
    name = f"api:{DOMAIN}:rooms"

    async def get(self, request):
        return web.json_response(await self.repo.list_rooms())

    async def post(self, request):
        data = await request.json()
        name = clean_str(data.get("name"))
        if not name:
            return json_error("Name required")
        if err := length_error(name, MAX_NAME_LEN, "Name"):
            return json_error(err)
        try:
            rid = await self.repo.create_room(name)
        except sqlite3.IntegrityError:
            return json_error("Room already exists")
        return web.json_response({"id": rid, "name": name})

    async def patch(self, request):
        data = await request.json()
        room_id, name = data.get("id"), clean_str(data.get("name"))
        if not room_id:
            return json_error("Room ID required")
        if not name:
            return json_error("Room name required")
        if err := length_error(name, MAX_NAME_LEN, "Name"):
            return json_error(err)
        try:
            count = await self.repo.update_room(room_id, name)
        except sqlite3.IntegrityError:
            return json_error("Room name already exists")
        if count == 0:
            return json_error("Room not found", 404)
        return web.json_response({"message": "Updated"})

    async def delete(self, request):
        data = await request.json()
        room_id = data.get("id")
        if not room_id:
            return json_error("Room ID required")
        count, refs = await self.repo.delete_room(room_id)
        if count == 0:
            return json_error("Room not found", 404)
        await _delete_images(self.hass, refs)
        return web.json_response({"message": "Deleted", "images_deleted": len(refs)})


# --------------------------------------------------------------------------- #
# Cupboards
# --------------------------------------------------------------------------- #
class CupboardsView(HInvView):
    url = f"/api/{DOMAIN}/cupboards"
    name = f"api:{DOMAIN}:cupboards"

    async def get(self, request):
        room = request.query.get("room")
        if not room:
            return json_error("Room required")
        return web.json_response(await self.repo.list_cupboards(room))

    async def post(self, request):
        data = await request.json()
        room = clean_str(data.get("room"))
        name = clean_str(data.get("name"))
        image = data.get("image", "") or ""
        if not room or not name:
            return json_error("Room and name required")
        if err := length_error(name, MAX_NAME_LEN, "Name"):
            return json_error(err)
        try:
            cid = await self.repo.create_cupboard(room, name, image)
        except sqlite3.IntegrityError:
            return json_error("Cupboard already exists")
        if cid is None:
            return json_error("Room not found", 404)
        return web.json_response({"id": cid, "name": name})

    async def patch(self, request):
        data = await request.json()
        cupboard_id = data.get("id")
        if not cupboard_id:
            return json_error("Cupboard ID required")
        name = data.get("name")
        image = data.get("image")
        if err := length_error(name, MAX_NAME_LEN, "Name"):
            return json_error(err)
        try:
            count, stale = await self.repo.update_cupboard(cupboard_id, name, image)
        except sqlite3.IntegrityError:
            return json_error("Cupboard name already exists")
        if count == 0:
            return json_error("Cupboard not found", 404)
        if stale:
            await _delete_images(self.hass, [stale])
        return web.json_response({"message": "Updated"})

    async def delete(self, request):
        data = await request.json()
        cupboard_id = data.get("id")
        if not cupboard_id:
            return json_error("Cupboard ID required")
        count, refs = await self.repo.delete_cupboard(cupboard_id)
        if count == 0:
            return json_error("Cupboard not found", 404)
        await _delete_images(self.hass, refs)
        return web.json_response({"message": "Deleted", "images_deleted": len(refs)})


# --------------------------------------------------------------------------- #
# Shelves
# --------------------------------------------------------------------------- #
class ShelvesView(HInvView):
    url = f"/api/{DOMAIN}/shelves"
    name = f"api:{DOMAIN}:shelves"

    async def get(self, request):
        room = request.query.get("room")
        cupboard = request.query.get("cupboard")
        if not room or not cupboard:
            return json_error("Room and cupboard required")
        return web.json_response(await self.repo.list_shelves(room, cupboard))

    async def post(self, request):
        data = await request.json()
        room = clean_str(data.get("room"))
        cupboard = clean_str(data.get("cupboard"))
        name = clean_str(data.get("name"))
        if not room or not cupboard or not name:
            return json_error("Room, cupboard and name required")
        if err := length_error(name, MAX_NAME_LEN, "Name"):
            return json_error(err)
        try:
            sid = await self.repo.create_shelf(room, cupboard, name)
        except sqlite3.IntegrityError:
            return json_error("Shelf already exists")
        if sid is None:
            return json_error("Cupboard not found", 404)
        return web.json_response({"id": sid, "name": name})

    async def patch(self, request):
        data = await request.json()
        shelf_id, name = data.get("id"), clean_str(data.get("name"))
        if not shelf_id:
            return json_error("Shelf ID required")
        if not name:
            return json_error("Shelf name required")
        if err := length_error(name, MAX_NAME_LEN, "Name"):
            return json_error(err)
        try:
            count = await self.repo.update_shelf(shelf_id, name)
        except sqlite3.IntegrityError:
            return json_error("Shelf name already exists")
        if count == 0:
            return json_error("Shelf not found", 404)
        return web.json_response({"message": "Updated"})

    async def delete(self, request):
        data = await request.json()
        shelf_id = data.get("id")
        if not shelf_id:
            return json_error("Shelf ID required")
        count, refs = await self.repo.delete_shelf(shelf_id)
        if count == 0:
            return json_error("Shelf not found", 404)
        await _delete_images(self.hass, refs)
        return web.json_response({"message": "Deleted", "images_deleted": len(refs)})


# --------------------------------------------------------------------------- #
# Organizers
# --------------------------------------------------------------------------- #
class OrganizersView(HInvView):
    url = f"/api/{DOMAIN}/organizers"
    name = f"api:{DOMAIN}:organizers"

    async def get(self, request):
        room = request.query.get("room")
        cupboard = request.query.get("cupboard")
        shelf = request.query.get("shelf")
        if not room or not cupboard or not shelf:
            return json_error("Room, cupboard and shelf required")
        data = await self.repo.list_organizers(room, cupboard, shelf)
        token_id = self.token_id(request)
        for o in data["organizers"]:
            o["image"] = img.build_image_url(self.hass, o["image"], token_id)
        return web.json_response(data)

    async def post(self, request):
        data = await request.json()
        room = clean_str(data.get("room"))
        cupboard = clean_str(data.get("cupboard"))
        shelf = clean_str(data.get("shelf"))
        name = clean_str(data.get("name"))
        image = data.get("image", "") or ""
        if not room or not cupboard or not shelf or not name:
            return json_error("All fields required")
        if err := length_error(name, MAX_NAME_LEN, "Name"):
            return json_error(err)
        try:
            oid = await self.repo.create_organizer(room, cupboard, shelf, name, image)
        except sqlite3.IntegrityError:
            return json_error("Organizer already exists")
        if oid is None:
            return json_error("Shelf not found", 404)
        return web.json_response({"id": oid, "name": name})

    async def patch(self, request):
        data = await request.json()
        organizer_id = data.get("id")
        if not organizer_id:
            return json_error("Organizer ID required")
        name = data.get("name")
        image = data.get("image")
        if err := length_error(name, MAX_NAME_LEN, "Name"):
            return json_error(err)
        move = None
        if data.get("room") and data.get("cupboard") and data.get("shelf"):
            move = (data["room"], data["cupboard"], data["shelf"])
        try:
            count, stale, error = await self.repo.update_organizer(
                organizer_id, name, image, move
            )
        except sqlite3.IntegrityError:
            return json_error("Organizer name already exists")
        if error:
            return json_error(error, 404)
        if count == 0:
            return json_error("Organizer not found", 404)
        if stale:
            await _delete_images(self.hass, [stale])
        return web.json_response({"message": "Updated"})

    async def delete(self, request):
        data = await request.json()
        organizer_id = data.get("id")
        if not organizer_id:
            return json_error("Organizer ID required")
        deleted, org_image, item_images, items_deleted = await self.repo.delete_organizer(
            organizer_id
        )
        if not deleted:
            return json_error("Organizer not found", 404)
        refs = ([org_image] if org_image else []) + list(item_images)
        await _delete_images(self.hass, refs)
        return web.json_response(
            {"message": "Deleted", "items_deleted": items_deleted, "images_deleted": len(refs)}
        )
