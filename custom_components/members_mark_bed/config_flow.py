"""Config flow."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback

from .const import (
    CONF_ACCESS_KEY,
    CONF_FOOT_MAX,
    CONF_HEAD_MAX,
    DEFAULT_FOOT_MAX,
    DEFAULT_HEAD_MAX,
    DEFAULT_HOST,
    DOMAIN,
)
from .protocol import BedClient, BedConnectionError

KEY_RE = re.compile(r"^[0-9a-fA-F]{32}$")


class BedConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_ACCESS_KEY].replace(" ", "").lower()
            if not KEY_RE.match(key):
                errors[CONF_ACCESS_KEY] = "invalid_key"
            else:
                client = BedClient(user_input[CONF_HOST], bytes.fromhex(key))
                try:
                    await client.connect()
                    device_id = client.device_id
                except (BedConnectionError, OSError):
                    errors["base"] = "cannot_connect"
                finally:
                    await client.close()
                if not errors:
                    await self.async_set_unique_id(device_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="Adjustable Bed",
                        data={CONF_HOST: user_input[CONF_HOST], CONF_ACCESS_KEY: key},
                    )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_ACCESS_KEY): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BedOptionsFlow()


class BedOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        rng = vol.All(int, vol.Range(min=100, max=60000))
        schema = vol.Schema(
            {
                vol.Required(CONF_HEAD_MAX, default=opts.get(CONF_HEAD_MAX, DEFAULT_HEAD_MAX)): rng,
                vol.Required(CONF_FOOT_MAX, default=opts.get(CONF_FOOT_MAX, DEFAULT_FOOT_MAX)): rng,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
