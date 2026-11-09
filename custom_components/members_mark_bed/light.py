"""Under-bed light. The bed only has a toggle; state comes from the status frame."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BedConfigEntry
from .entity import BedEntity
from .protocol import KEY_LIGHT


async def async_setup_entry(
    hass: HomeAssistant, entry: BedConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([BedLight(entry, entry.runtime_data)])


class BedLight(BedEntity, LightEntity):
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, entry, client) -> None:  # noqa: ANN001
        super().__init__(entry, client, "light")

    @property
    def is_on(self) -> bool | None:
        return self.client.status.get("light")

    async def _set(self, on: bool) -> None:
        if self.is_on == on:
            return
        await self.client.press(KEY_LIGHT)
        await self.client.refresh(0.8)
        if self.is_on != on:          # missed the toggle once; try again
            await self.client.press(KEY_LIGHT)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
