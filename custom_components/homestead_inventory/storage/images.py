"""Image handling: validation, resize, storage, deletion, and signed URLs.

Security notes:

* Uploads are size-capped *before* decoding, validated as real images with
  Pillow, and always re-encoded to JPEG (a malformed or non-image payload is
  rejected, never stored verbatim).
* Images are served from a private API path, and the browser is handed a
  **signed** URL (HA ``async_sign_path``) rather than the user's access token
  in the query string. The signature is an HMAC tied to the requesting
  refresh token and expires; nothing reusable leaks into the DOM or logs.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import timedelta
from io import BytesIO

try:  # public re-export on current HA
    from homeassistant.components.http import async_sign_path
except ImportError:  # older layouts expose it from the auth module
    from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant

from ..const import DOMAIN, IMAGES_PATH, IMAGE_URL_TTL_SECONDS

_LOGGER = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB hard cap on a single upload
MAX_WIDTH = 1600
MAX_HEIGHT = 1200
JPEG_QUALITY = 85

_DIACRITICS = {
    "ă": "a", "â": "a", "î": "i", "ș": "s", "ț": "t",
    "Ă": "A", "Â": "A", "Î": "I", "Ș": "S", "Ț": "T",
}


def sanitize_filename(text: str) -> str:
    """Reduce arbitrary text to a safe, lowercase filename fragment."""
    if not text:
        return "unknown"
    for old, new in _DIACRITICS.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-zA-Z0-9\s_-]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    text = text[:50]
    return text.lower() if text else "unknown"


def build_filename(parts: list[str]) -> str:
    """Build a unique, human-readable .jpg filename from location parts."""
    cleaned = [sanitize_filename(p) for p in parts if p and p != "null"]
    short = uuid.uuid4().hex[:8]
    if cleaned:
        return f"{'_'.join(cleaned)}_{short}.jpg"
    return f"{uuid.uuid4().hex}.jpg"


def resize_to_jpeg(image_data: bytes) -> bytes:
    """Validate + normalize an uploaded image to a bounded JPEG.

    Raises ValueError if the payload is not a decodable image.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    # Deliberate decompression-bomb cap (Pillow's default only warns). A crafted
    # high-pixel image raises DecompressionBombError, which we surface as a clean
    # "not a valid image" 400 instead of an unexpected 500.
    Image.MAX_IMAGE_PIXELS = 64_000_000

    try:
        # verify() on a fresh handle confirms it is a real image without decoding all of it.
        Image.open(BytesIO(image_data)).verify()
        img = Image.open(BytesIO(image_data))
        img = ImageOps.exif_transpose(img)
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as err:
        raise ValueError("Uploaded file is not a valid image") from err

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")
    img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)

    out = BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


def images_dir(hass: HomeAssistant) -> str:
    path = hass.config.path(IMAGES_PATH)
    os.makedirs(path, exist_ok=True)
    return path


def write_image(hass: HomeAssistant, filename: str, data: bytes) -> None:
    """Blocking file write — call via async_add_executor_job."""
    with open(os.path.join(images_dir(hass), filename), "wb") as fh:
        fh.write(data)


def _bare_filename(image_ref: str) -> str | None:
    """Extract a bare filename from a stored reference, or None to skip."""
    if not image_ref:
        return None
    if image_ref.startswith("/local/"):
        return None  # not ours to manage
    if image_ref.startswith(f"/api/{DOMAIN}/images/"):
        return image_ref.split("/")[-1].split("?")[0]
    return image_ref


def delete_image_file(hass: HomeAssistant, image_ref: str) -> None:
    """Remove an image file from disk. Tolerant of missing files. Blocking."""
    name = _bare_filename(image_ref)
    if not name or ".." in name or "/" in name:
        return
    full = os.path.join(images_dir(hass), name)
    try:
        if os.path.exists(full):
            os.remove(full)
            _LOGGER.debug("Deleted image %s", name)
    except OSError as err:
        _LOGGER.error("Error deleting image %s: %s", name, err)


def build_image_url(
    hass: HomeAssistant, image_ref: str, refresh_token_id: str | None
) -> str:
    """Return a signed, expiring URL for an image reference (or pass-through)."""
    if not image_ref:
        return ""
    if image_ref.startswith(("http://", "https://", "/local/")):
        return image_ref
    name = _bare_filename(image_ref) or image_ref
    path = f"/api/{DOMAIN}/images/{name}"
    try:
        return async_sign_path(
            hass,
            path,
            timedelta(seconds=IMAGE_URL_TTL_SECONDS),
            refresh_token_id=refresh_token_id,
        )
    except Exception as err:  # noqa: BLE001 - never let URL signing break a listing
        _LOGGER.warning("Could not sign image URL for %s: %s", name, err)
        return path
