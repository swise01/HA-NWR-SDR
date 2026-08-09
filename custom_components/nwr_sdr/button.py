"""Buttons for HA-NWR-SDR."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    """Set up NWR buttons."""
    runtime: NwrSdrRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NwrRestartButton(runtime)])


class NwrRestartButton(ButtonEntity):
    """Restart the managed SDR pipeline."""

    _attr_has_entity_name = True
    _attr_name = "Restart Radio Pipeline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, runtime: NwrSdrRuntime) -> None:
        self._runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_restart_pipeline"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name="NOAA Weather Radio",
        )
        self._remove_listener: Callable[[], None] | None = None

    @property
    def available(self) -> bool:
        """Return whether the parser supports controls."""
        return self._runtime.parser_status == "running" and bool(
            self._runtime.control_state
        )

    async def async_press(self) -> None:
        """Request a controlled pipeline restart."""
        await self._runtime.async_send_control("restart")

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
