"""Massage state and diagnostic sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BedConfigEntry
from .entity import BedEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: BedConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    c = entry.runtime_data
    async_add_entities(
        [
            MassageRemaining(entry, c),
            StatusSensor(entry, c, "head_raw", diagnostic=True),
            StatusSensor(entry, c, "foot_raw", diagnostic=True),
            StatusFrame(entry, c),
        ]
    )


class StatusSensor(BedEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry, client, key: str, diagnostic: bool = False) -> None:  # noqa: ANN001
        super().__init__(entry, client, key)
        self._key = key
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        return self.client.status.get(self._key)


class MassageRemaining(BedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, entry, client) -> None:  # noqa: ANN001
        super().__init__(entry, client, "massage_remaining")

    @property
    def native_value(self) -> int | None:
        st = self.client.status
        if not st:
            return None
        return st.get("massage_remaining", 0) if st.get("massage_timer") is not None else 0


class StatusFrame(BedEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry, client) -> None:  # noqa: ANN001
        super().__init__(entry, client, "status_frame")

    @property
    def native_value(self) -> str | None:
        raw = self.client.status.get("raw")
        return raw[:255] if raw else None
