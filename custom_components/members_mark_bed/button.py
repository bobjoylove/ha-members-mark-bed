"""Preset and massage buttons."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BedConfigEntry
from .entity import BedEntity
from .protocol import (
    KEY_FLAT,
    KEY_MASSAGE_OFF,
    KEY_MEMORY_1,
    KEY_MEMORY_2,
    KEY_MEMORY_3,
    KEY_MEMORY_4,
    KEY_ZERO_G,
    SAVE_HOLD_SECONDS,
)

BUTTONS = {
    "flat": (KEY_FLAT, "mdi:bed"),
    "zero_g": (KEY_ZERO_G, "mdi:sofa-single"),
    "memory_1": (KEY_MEMORY_1, "mdi:numeric-1-box"),
    "memory_2": (KEY_MEMORY_2, "mdi:numeric-2-box"),
    "memory_3": (KEY_MEMORY_3, "mdi:numeric-3-box"),
    "memory_4": (KEY_MEMORY_4, "mdi:numeric-4-box"),
    "massage_off": (KEY_MASSAGE_OFF, "mdi:vibrate-off"),
    "stop": (0, "mdi:stop"),
}


SAVE_PRESETS = ("memory_1", "memory_2", "memory_3", "memory_4")


async def async_setup_entry(
    hass: HomeAssistant, entry: BedConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    entities: list[ButtonEntity] = [
        BedButton(entry, client, k, code, icon) for k, (code, icon) in BUTTONS.items()
    ]
    entities += [SavePresetButton(entry, client, k, BUTTONS[k][0]) for k in SAVE_PRESETS]
    async_add_entities(entities)


class BedButton(BedEntity, ButtonEntity):
    def __init__(self, entry, client, key: str, code: int, icon: str) -> None:  # noqa: ANN001
        super().__init__(entry, client, key)
        self._code = code
        self._attr_icon = icon

    async def async_press(self) -> None:
        if self._code == 0:
            # Stop any held motor and send "no button" frames.
            await self.client.press(0, repeats=0)
        else:
            await self.client.press(self._code)


class SavePresetButton(BedEntity, ButtonEntity):
    """Store the bed's current position in a preset (same as holding it in the app)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:content-save"

    def __init__(self, entry, client, key: str, code: int) -> None:  # noqa: ANN001
        super().__init__(entry, client, f"save_{key}")
        self._code = code

    async def async_press(self) -> None:
        await self.client.hold_for(self._code, SAVE_HOLD_SECONDS)
