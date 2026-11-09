"""Head and foot motors as covers with position."""
from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BedConfigEntry
from .const import CONF_FOOT_MAX, CONF_HEAD_MAX, DEFAULT_FOOT_MAX, DEFAULT_HEAD_MAX
from .entity import BedEntity
from .protocol import KEY_FOOT_DOWN, KEY_FOOT_UP, KEY_HEAD_DOWN, KEY_HEAD_UP

# Readings jitter by up to ~130 raw units at rest, so allow some slack.
TOLERANCE = 150


async def async_setup_entry(
    hass: HomeAssistant, entry: BedConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    opts = entry.options
    async_add_entities(
        [
            SectionCover(entry, client, "head", KEY_HEAD_UP, KEY_HEAD_DOWN, "head_raw",
                         opts.get(CONF_HEAD_MAX, DEFAULT_HEAD_MAX)),
            SectionCover(entry, client, "foot", KEY_FOOT_UP, KEY_FOOT_DOWN, "foot_raw",
                         opts.get(CONF_FOOT_MAX, DEFAULT_FOOT_MAX)),
        ]
    )


class SectionCover(BedEntity, CoverEntity):
    """A bed section. Open = raise, close = lower."""

    _attr_device_class = CoverDeviceClass.DAMPER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, entry, client, key, up, down, field, maximum) -> None:  # noqa: ANN001
        super().__init__(entry, client, key)
        self._up, self._down, self._field = up, down, field
        self._max = max(int(maximum), 1)
        self._moving: int | None = None

    def _raw(self) -> int | None:
        raw = self.client.status.get(self._field)
        if raw is not None and raw > self._max and raw < 0xF000:
            self._max = raw          # learn the real full-raise value
        return raw

    @property
    def current_cover_position(self) -> int | None:
        raw = self._raw()
        if raw is None:
            return None
        if raw <= TOLERANCE:
            return 0
        return max(0, min(100, round(raw * 100 / self._max)))

    @property
    def is_closed(self) -> bool | None:
        raw = self._raw()
        return None if raw is None else raw <= TOLERANCE

    @property
    def is_opening(self) -> bool:
        return self._moving == self._up

    @property
    def is_closing(self) -> bool:
        return self._moving == self._down

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"raw_position": self.client.status.get(self._field), "calibrated_max": self._max}

    async def _run(self, key: int, until) -> None:  # noqa: ANN001
        self._moving = key
        self.async_write_ha_state()
        await self.client.start_hold(key, until=until)
        task = self.client._hold_task  # noqa: SLF001

        def _done(_t) -> None:  # noqa: ANN001
            if self._moving == key:
                self._moving = None
                self.async_write_ha_state()

        if task:
            task.add_done_callback(_done)
        else:
            _done(None)

    async def async_open_cover(self, **kwargs: Any) -> None:
        # Hold until the reading stops climbing is not knowable; the bed's own
        # limit switch stops the motor, and the hold times out after 40 s.
        await self._run(self._up, until=None)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._run(self._down, until=lambda: (self._raw() or 0) <= TOLERANCE)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self.client.stop()
        self._moving = None
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        target = kwargs[ATTR_POSITION] * self._max / 100
        raw = self._raw()
        if raw is None or abs(raw - target) <= TOLERANCE:
            return
        if target > raw:
            await self._run(self._up, until=lambda: (self._raw() or 0) >= target - TOLERANCE)
        else:
            await self._run(self._down, until=lambda: (self._raw() or 0) <= target + TOLERANCE)
