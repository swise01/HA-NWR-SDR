"""Sensors for HA-NWR-SDR."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NwrSdrRuntime
from .const import (
    ATTR_COUNTY_CODES,
    ATTR_EFFECTIVE_SEVERITY,
    ATTR_EFFECTIVE_SEVERITY_LABEL,
    ATTR_EVENT_CODE,
    ATTR_EVENT_NAME,
    ATTR_EXPIRY_UTC,
    ATTR_ISSUE_UTC,
    ATTR_RECEIVED_UTC,
    ATTR_SEVERITY,
    ATTR_SEVERITY_LABEL,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)
from .payload import parse_utc


@dataclass(frozen=True, kw_only=True)
class NwrSensorDescription(SensorEntityDescription):
    """NWR sensor description."""

    value_fn: Callable[[NwrSdrRuntime], Any]


SENSORS = (
    NwrSensorDescription(
        key="parser_status",
        name="Parser Status",
        device_class=SensorDeviceClass.ENUM,
        options=["running", "error", "offline"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda rt: rt.parser_status,
    ),
    NwrSensorDescription(
        key="audio_url",
        name="Audio URL",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda rt: rt.audio_url,
    ),
    NwrSensorDescription(
        key="event_code",
        name="Event Code",
        value_fn=lambda rt: rt.alert.get(ATTR_EVENT_CODE),
    ),
    NwrSensorDescription(
        key="event_name",
        name="Event Name",
        value_fn=lambda rt: rt.alert.get(ATTR_EVENT_NAME),
    ),
    NwrSensorDescription(
        key="severity",
        name="SAME Severity",
        value_fn=lambda rt: rt.alert.get(ATTR_SEVERITY),
    ),
    NwrSensorDescription(
        key="severity_label",
        name="SAME Severity Label",
        value_fn=lambda rt: rt.alert.get(ATTR_SEVERITY_LABEL),
    ),
    NwrSensorDescription(
        key="effective_severity",
        name="Effective Severity",
        value_fn=lambda rt: rt.alert.get(ATTR_EFFECTIVE_SEVERITY),
    ),
    NwrSensorDescription(
        key="effective_severity_label",
        name="Effective Severity Label",
        value_fn=lambda rt: rt.alert.get(ATTR_EFFECTIVE_SEVERITY_LABEL),
    ),
    NwrSensorDescription(
        key="county_codes",
        name="County Codes",
        value_fn=lambda rt: rt.alert.get(ATTR_COUNTY_CODES),
    ),
    NwrSensorDescription(
        key="expires",
        name="Alert Expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda rt: parse_utc(rt.alert.get(ATTR_EXPIRY_UTC)),
    ),
    NwrSensorDescription(
        key="issued",
        name="Alert Issued",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda rt: parse_utc(rt.alert.get(ATTR_ISSUE_UTC)),
    ),
    NwrSensorDescription(
        key="received",
        name="Alert Received",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda rt: parse_utc(rt.alert.get(ATTR_RECEIVED_UTC)),
    ),
    NwrSensorDescription(
        key="eom_utc",
        name="EOM Received",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda rt: parse_utc(rt.eom_utc),
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
            "issued",
            "received",
        }:
            return dict(self._runtime.alert)
        return None
