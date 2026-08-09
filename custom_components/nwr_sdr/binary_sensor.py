"""Binary sensors for HA-NWR-SDR."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NwrSdrRuntime
from .const import DOMAIN, MANUFACTURER, MODEL


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    runtime: NwrSdrRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NwrAlertActiveBinarySensor(runtime)])


class NwrAlertActiveBinarySensor(BinarySensorEntity):
    """Active NWR alert binary sensor."""

    _attr_has_entity_name = True
    _attr_name = "Alert Active"
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, runtime: NwrSdrRuntime) -> None:
        self._runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_alert_active"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name="NOAA Weather Radio",
        )
        self._remove_listener: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self._remove_listener = self._runtime.async_add_listener(
            self._handle_runtime_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Remove update listener."""
        if self._remove_listener:
            self._remove_listener()

    @callback
    def _handle_runtime_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return whether an alert is active."""
        return self._runtime.active_alert
