"""Member's Mark WiFi adjustable base - local control."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_ACCESS_KEY
from .protocol import BedClient, BedConnectionError

PLATFORMS = [Platform.BUTTON, Platform.COVER, Platform.LIGHT, Platform.SELECT, Platform.SENSOR]

type BedConfigEntry = ConfigEntry[BedClient]


async def async_setup_entry(hass: HomeAssistant, entry: BedConfigEntry) -> bool:
    client = BedClient(entry.data[CONF_HOST], bytes.fromhex(entry.data[CONF_ACCESS_KEY]))
    try:
        await client.connect()
    except (BedConnectionError, OSError) as err:
        await client.close()
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BedConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.close()
    return ok


async def _async_reload(hass: HomeAssistant, entry: BedConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
