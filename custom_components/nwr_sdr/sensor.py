"""Sensors for HA-NWR-SDR."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NwrSdrRuntime
from .const import (
    ATTR_COUNTY_CODES,
    ATTR_EFFECTIVE_SEVERITY,
    ATTR_EFFECTIVE_SEVERITY_LABEL,
    ATTR_EVENT_CODE,
    ATTR_EVENT_NAME,
    ATTR_EXPIRY_UTC,
    ATTR_SEVERITY,
    ATTR_SEVERITY_LABEL,
    DOMAIN,
)


@dataclass(frozen=True)
class NwrSensorDescription(SensorEntityDescription):
    """NWR sensor description."""

    value_fn: Callable[[NwrSdrRuntime], Any]


SENSORS = (
    NwrSensorDescription(
        key="parser_status",
        name="NWR Parser Status",
        value_fn=lambda rt: rt.parser_status,
    ),
    NwrSensorDescription(
        key="audio_url",
        name="NWR Audio URL",
        value_fn=lambda rt: rt.audio_url,
    ),
    NwrSensorDescription(
        key="event_code",
        name="NWR Event Code",
        value_fn=lambda rt: rt.alert.get(ATTR_EVENT_CODE),
    ),
    NwrSensorDescription(
        key="event_name",
        name="NWR Event Name",
        value_fn=lambda rt: rt.alert.get(ATTR_EVENT_NAME),
    ),
    NwrSensorDescription(
        key="severity",
        name="NWR SAME Severity",
        value_fn=lambda rt: rt.alert.get(ATTR_SEVERITY),
    ),
    NwrSensorDescription(
        key="severity_label",
        name="NWR SAME Severity Label",
        value_fn=lambda rt: rt.alert.get(ATTR_SEVERITY_LABEL),
    ),
    NwrSensorDescription(
        key="effective_severity",
        name="NWR Effective Severity",
        value_fn=lambda rt: rt.alert.get(ATTR_EFFECTIVE_SEVERITY),
    ),
    NwrSensorDescription(
        key="effective_severity_label",
        name="NWR Effective Severity Label",
        value_fn=lambda rt: rt.alert.get(ATTR_EFFECTIVE_SEVERITY_LABEL),
    ),
    NwrSensorDescription(
        key="county_codes",
        name="NWR County Codes",
        value_fn=lambda rt: rt.alert.get(ATTR_COUNTY_CODES),
    ),
    NwrSensorDescription(
        key="expires",
        name="NWR Alert Expires",
        value_fn=lambda rt: rt.alert.get(ATTR_EXPIRY_UTC),
    ),
    NwrSensorDescription(
        key="eom_utc", name="NWR EOM Received", value_fn=lambda rt: rt.eom_utc
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    runtime: NwrSdrRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(NwrSensor(runtime, description) for description in SENSORS)


class NwrSensor(SensorEntity):
    """HA-NWR-SDR sensor."""

    _attr_has_entity_name = True

    def __init__(
        self, runtime: NwrSdrRuntime, description: NwrSensorDescription
    ) -> None:
        self._runtime = runtime
        self.entity_description = description
        self._attr_unique_id = f"{runtime.entry.entry_id}_{description.key}"
        self._attr_name = description.name
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
    def native_value(self) -> Any:
        """Return sensor value."""
        return self.entity_description.value_fn(self._runtime)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return alert attributes on alert-related sensors."""
        if self.entity_description.key in {
            "event_code",
            "event_name",
            "severity",
            "severity_label",
            "effective_severity",
            "effective_severity_label",
            "county_codes",
            "expires",
        }:
            return dict(self._runtime.alert)
        return None
