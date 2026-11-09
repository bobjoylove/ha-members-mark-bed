"""Shared entity base."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .protocol import BedClient


class BedEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, client: BedClient, key: str) -> None:
        self.client = client
        self.entry = entry
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name="Adjustable Bed",
            manufacturer="Member's Mark (Keeson / XLink)",
            model="Luxury Adjustable Base (WiFi)",
        )

    @property
    def available(self) -> bool:
        return self.client.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.client.add_listener(self.async_write_ha_state))
