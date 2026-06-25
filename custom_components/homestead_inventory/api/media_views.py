"""Image upload + serving views."""

from __future__ import annotations

import logging
import os
import re

from aiohttp import web

from ..const import DOMAIN
from ..storage import images as img
from .base import HInvView, json_error

_LOGGER = logging.getLogger(__name__)

# Stored images are always sanitized lowercase + a uuid suffix + ".jpg".
# Anything else (traversal, null bytes, backslashes, odd chars) is rejected.
_VALID_IMAGE_NAME = re.compile(r"^[a-z0-9_-]+\.jpg$")


class UploadView(HInvView):
    url = f"/api/{DOMAIN}/upload"
    name = f"api:{DOMAIN}:upload"

    async def post(self, request):
        # Reject oversized uploads up front (before buffering into memory).
        if request.content_length and request.content_length > img.MAX_UPLOAD_BYTES:
            return json_error("Image too large", 413)
        try:
            reader = await request.multipart()
            field = await reader.next()
            if field is None:
                return json_error("No file")

            # Read in bounded chunks so an attacker can't force a huge buffer
            # into memory before the size check (Content-Length is spoofable /
            # absent for chunked uploads).
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = await field.read_chunk(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > img.MAX_UPLOAD_BYTES:
                    return json_error("Image too large", 413)
                chunks.append(chunk)
            raw = b"".join(chunks)
            if not raw:
                return json_error("No file")

            try:
                jpeg = await self.hass.async_add_executor_job(img.resize_to_jpeg, raw)
            except ValueError:
                return json_error("Uploaded file is not a valid image", 400)

            q = request.query
            filename = img.build_filename(
                [
                    q.get("room", ""),
                    q.get("cupboard", ""),
                    q.get("shelf", ""),
                    q.get("organizer", ""),
                    q.get("item", ""),
                ]
            )
            await self.hass.async_add_executor_job(
                img.write_image, self.hass, filename, jpeg
            )

            old_image = q.get("old_image", "")
            if old_image and old_image != filename:
                await self.hass.async_add_executor_job(
                    img.delete_image_file, self.hass, old_image
                )

            _LOGGER.debug(
                "Uploaded image %s (%.0fKB -> %.0fKB)",
                filename, len(raw) / 1024, len(jpeg) / 1024,
            )
            return web.json_response({"path": filename})
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Upload error: %s", err, exc_info=True)
            return json_error("Upload failed", 500)


class ImageView(HInvView):
    """Serve a stored image.

    ``requires_auth`` is True, so HA's middleware accepts either a Bearer
    token or a valid **signed URL** (what the frontend uses for <img> tags).
    No token ever appears in the image URL.
    """

    url = f"/api/{DOMAIN}/images/{{filename}}"
    name = f"api:{DOMAIN}:image"

    async def get(self, request, filename):
        if not filename or not _VALID_IMAGE_NAME.match(filename):
            return web.Response(status=400, text="Invalid filename")

        path = os.path.join(img.images_dir(self.hass), filename)
        if not os.path.exists(path):
            return web.Response(status=404, text="Image not found")

        data = await self.hass.async_add_executor_job(_read, path)
        return web.Response(
            body=data,
            content_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=86400"},
        )


def _read(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()
