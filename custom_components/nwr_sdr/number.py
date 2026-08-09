"""Number entities for HA-NWR-SDR."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NwrSdrRuntime
from .const import DOMAIN, MANUFACTURER, MODEL
from .control import (
    GAIN_MAX,
    GAIN_MIN,
    GAIN_STEP,
    PPM_MAX,
    PPM_MIN,
    normalize_gain,
    normalize_ppm,
)


@dataclass(frozen=True, kw_only=True)
class NwrNumberDescription(NumberEntityDescription):
    """NWR control number description."""

    command: str
    value_key: str
    normalize: Callable[[Any], float | int]


NUMBERS = (
    NwrNumberDescription(
        key="gain",
        name="SDR Gain",
        command="set_gain",
        value_key="gain",
        native_min_value=GAIN_MIN,
        native_max_value=GAIN_MAX,
        native_step=GAIN_STEP,
        mode=NumberMode.BOX,
        normalize=normalize_gain,
        entity_category=EntityCategory.CONFIG,
    ),
    NwrNumberDescription(
        key="ppm",
        name="SDR PPM Correction",
        command="set_ppm",
        value_key="ppm",
        native_min_value=PPM_MIN,
        native_max_value=PPM_MAX,
        native_step=1,
        mode=NumberMode.BOX,
        normalize=normalize_ppm,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NWR numbers."""
    runtime: NwrSdrRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(NwrControlNumber(runtime, description) for description in NUMBERS)


class NwrControlNumber(NumberEntity):
    """A bounded NWR radio setting."""

    _attr_has_entity_name = True

    def __init__(
        self, runtime: NwrSdrRuntime, description: NwrNumberDescription
    ) -> None:
        self._runtime = runtime
        self.entity_description = description
        self._attr_unique_id = f"{runtime.entry.entry_id}_{description.key}"
        self._attr_name = description.name
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
    def native_value(self) -> float | int | None:
        """Return the acknowledged setting."""
        return self._runtime.control_state.get(self.entity_description.value_key)

    async def async_set_native_value(self, value: float) -> None:
        """Set a bounded radio value."""
        normalized = self.entity_description.normalize(value)
        await self._runtime.async_send_control(
            self.entity_description.command, normalized
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
