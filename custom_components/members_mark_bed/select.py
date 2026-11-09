"""Massage intensity / pattern / timer as dropdowns.

The bed only has "cycle" buttons, so each select presses its button until the
status frame reports the chosen value.
"""
from __future__ import annotations

import asyncio

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BedConfigEntry
from .entity import BedEntity
from .protocol import (
    KEY_MASSAGE_FOOT,
    KEY_MASSAGE_HEAD,
    KEY_MASSAGE_OFF,
    KEY_MASSAGE_PATTERN,
    KEY_MASSAGE_TIMER,
)

# Status value -> option. Intensity cycles off -> 1 -> 3 -> 6 -> off.
INTENSITY = {0: "off", 1: "low", 3: "medium", 6: "high"}
PATTERN = {0: "pattern_1", 1: "pattern_2", 2: "pattern_3", 3: "pattern_4"}
TIMER = {None: "off", 1: "10_min", 2: "20_min", 3: "30_min"}


async def async_setup_entry(
    hass: HomeAssistant, entry: BedConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    c = entry.runtime_data
    async_add_entities(
        [
            CycleSelect(entry, c, "massage_head", KEY_MASSAGE_HEAD, INTENSITY, "mdi:vibrate"),
            CycleSelect(entry, c, "massage_foot", KEY_MASSAGE_FOOT, INTENSITY, "mdi:vibrate"),
            CycleSelect(entry, c, "massage_pattern", KEY_MASSAGE_PATTERN, PATTERN, "mdi:sine-wave"),
            CycleSelect(entry, c, "massage_timer", KEY_MASSAGE_TIMER, TIMER, "mdi:timer-outline"),
        ]
    )


class CycleSelect(BedEntity, SelectEntity):
    def __init__(self, entry, client, field: str, key: int, mapping: dict, icon: str) -> None:  # noqa: ANN001
        super().__init__(entry, client, f"{field}_select")
        self._field, self._key, self._map = field, key, mapping
        self._attr_options = list(dict.fromkeys(mapping.values()))
        self._attr_icon = icon

    def _value(self):  # noqa: ANN202
        return self.client.status.get(self._field)

    @property
    def current_option(self) -> str | None:
        st = self.client.status
        if not st:
            return None
        # Pattern means nothing while massage is off.
        if self._field == "massage_pattern" and st.get("massage_timer") is None:
            return None
        return self._map.get(self._value())

    async def async_select_option(self, option: str) -> None:
        # A newer pick replaces one still in progress, so two picks never
        # press the cycle button on top of each other.
        self._gen = gen = getattr(self, "_gen", 0) + 1
        prev = getattr(self, "_task", None)
        if prev and not prev.done():
            prev.cancel()
            try:
                await prev
            except asyncio.CancelledError:
                pass
        task = self._task = asyncio.ensure_future(self._select(option))
        try:
            await task
        except asyncio.CancelledError:
            if self._gen == gen:        # not superseded: we were cancelled ourselves
                raise
            # otherwise a newer pick superseded this one; finish quietly

    def _other_zone_off(self) -> bool:
        other = {"massage_head": "massage_foot", "massage_foot": "massage_head"}.get(self._field)
        return other is not None and not self.client.status.get(other)

    async def _select(self, option: str) -> None:
        await self.client.refresh(0.4)          # make sure we start from the real value
        if option == "off" and self.current_option != "off" and (
            self._field == "massage_timer" or self._other_zone_off()
        ):
            # Direct "massage off" (no cycling through the higher levels).
            await self.client.press(KEY_MASSAGE_OFF)
            await self.client.refresh(0.6)
            return
        for _ in range(len(self._map)):
            if self.current_option == option:
                return
            before = self._value()
            await self.client.press(self._key, repeats=2)
            # Keep polling (the bed only reports when spoken to) until the
            # value moves one step, up to 3 s. Never press again before that.
            for _ in range(15):
                await self.client.refresh(0.2)
                if self._value() != before:
                    break
            else:
                return                           # bed didn't react; don't keep cycling
            await self.client.refresh(0.4)       # let it settle before deciding
