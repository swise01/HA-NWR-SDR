"""Select entities for HA-NWR-SDR."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NwrSdrRuntime
from .const import DOMAIN, MANUFACTURER, MODEL
from .control import NOAA_FREQUENCIES, normalize_frequency


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NWR selects."""
    runtime: NwrSdrRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NwrFrequencySelect(runtime)])


class NwrFrequencySelect(SelectEntity):
    """Select one of the seven NOAA Weather Radio channels."""

    _attr_has_entity_name = True
    _attr_name = "NOAA Channel"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(NOAA_FREQUENCIES)

    def __init__(self, runtime: NwrSdrRuntime) -> None:
        self._runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_frequency"
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

    @property
    def current_option(self) -> str | None:
        """Return the acknowledged frequency."""
        return self._runtime.control_state.get("frequency")

    async def async_select_option(self, option: str) -> None:
        """Set the receiver frequency."""
        await self._runtime.async_send_control(
            "set_frequency", normalize_frequency(option)
        )

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
