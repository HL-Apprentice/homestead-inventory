"""Config + options flow for Homestead Inventory."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, INTEGRATION_NAME

_LOGGER = logging.getLogger(__name__)


class HomesteadInventoryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Single-instance config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title=INTEGRATION_NAME, data={}, options=user_input
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional("allow_structure_modification", default=True): bool,
                    vol.Optional("require_admin", default=False): bool,
                    vol.Optional("enable_barcode_lookup", default=False): bool,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HomesteadInventoryOptionsFlow()


class HomesteadInventoryOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "allow_structure_modification",
                        default=opts.get("allow_structure_modification", True),
                    ): bool,
                    vol.Optional(
                        "require_admin", default=opts.get("require_admin", False)
                    ): bool,
                    vol.Optional(
                        "enable_barcode_lookup",
                        default=opts.get("enable_barcode_lookup", False),
                    ): bool,
                }
            ),
        )
