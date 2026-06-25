"""Constants for the Homestead Inventory integration."""

DOMAIN = "homestead_inventory"
INTEGRATION_NAME = "Homestead Inventory"

# Folder (under the HA config dir) that holds this integration's private data.
# Both the SQLite database and uploaded images live here.
DATA_DIR = DOMAIN
DB_FILENAME = "inventory.db"
IMAGES_SUBDIR = "images"

# Relative path used by the sensor platform via hass.config.path(...).
DB_PATH = f"{DATA_DIR}/{DB_FILENAME}"
IMAGES_PATH = f"{DATA_DIR}/{IMAGES_SUBDIR}"

# Events fired on the HA bus (for automations).
EVENT_LOW_STOCK = f"{DOMAIN}_low_stock"
EVENT_ITEM_CONSUMED = f"{DOMAIN}_item_consumed"

# How long a signed image URL stays valid. Long enough to browse a session,
# short enough that a leaked URL is useless tomorrow.
IMAGE_URL_TTL_SECONDS = 24 * 60 * 60  # 24h
