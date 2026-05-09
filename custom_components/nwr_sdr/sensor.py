"""Sensors for HA-NWR-SDR."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity
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
class SensorDescription:
    """NWR sensor description."""

    key: str
    name: str
    value_fn: Callable[[NwrSdrRuntime], Any]


SENSORS = (
    SensorDescription("parser_status", "NWR Parser Status", lambda rt: rt.parser_status),
    SensorDescription("audio_url", "NWR Audio URL", lambda rt: rt.audio_url),
    SensorDescription(
        "event_code", "NWR Event Code", lambda rt: rt.alert.get(ATTR_EVENT_CODE)
    ),
    SensorDescription(
        "event_name", "NWR Event Name", lambda rt: rt.alert.get(ATTR_EVENT_NAME)
    ),
    SensorDescription(
        "severity", "NWR SAME Severity", lambda rt: rt.alert.get(ATTR_SEVERITY)
    ),
    SensorDescription(
        "severity_label",
        "NWR SAME Severity Label",
        lambda rt: rt.alert.get(ATTR_SEVERITY_LABEL),
    ),
    SensorDescription(
        "effective_severity",
        "NWR Effective Severity",
        lambda rt: rt.alert.get(ATTR_EFFECTIVE_SEVERITY),
    ),
    SensorDescription(
        "effective_severity_label",
        "NWR Effective Severity Label",
        lambda rt: rt.alert.get(ATTR_EFFECTIVE_SEVERITY_LABEL),
    ),
    SensorDescription(
        "county_codes", "NWR County Codes", lambda rt: rt.alert.get(ATTR_COUNTY_CODES)
    ),
    SensorDescription(
        "expires", "NWR Alert Expires", lambda rt: rt.alert.get(ATTR_EXPIRY_UTC)
    ),
    SensorDescription("eom_utc", "NWR EOM Received", lambda rt: rt.eom_utc),
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
        self, runtime: NwrSdrRuntime, description: SensorDescription
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
