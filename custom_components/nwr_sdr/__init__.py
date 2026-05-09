"""HA-NWR-SDR integration."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import event as event_helper
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_COUNTIES,
    ATTR_COUNTY_CODES,
    ATTR_EVENT_CODE,
    ATTR_EVENT_NAME,
    ATTR_EFFECTIVE_SEVERITY,
    ATTR_EFFECTIVE_SEVERITY_LABEL,
    ATTR_EXPIRY_UTC,
    ATTR_ISSUE_UTC,
    ATTR_RAW,
    ATTR_REMAINING_SECONDS,
    ATTR_SEVERITY,
    ATTR_SEVERITY_LABEL,
    CONF_TEST_EFFECTIVE_SEVERITY,
    CONF_TOPIC_ROOT,
    DEFAULT_TEST_EFFECTIVE_SEVERITY,
    DEFAULT_TOPIC_ROOT,
    DOMAIN,
    EVENT_ALERT_RECEIVED,
    EVENT_ALERT_EXPIRED,
    EVENT_EOM_RECEIVED,
    EVENT_NAMES,
    SEVERITY_LABELS,
    TIER_BY_CODE,
    TOPIC_AUDIO_URL,
    TOPIC_EOM,
    TOPIC_SAME_ALERT,
    TOPIC_STATUS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


@dataclass
class NwrSdrRuntime:
    """Runtime data shared by NWR entities."""

    hass: HomeAssistant
    entry: ConfigEntry
    topic_root: str
    listeners: list[Callable[[], None]] = field(default_factory=list)
    unsubscribers: list[Callable[[], None]] = field(default_factory=list)
    expiry_unsubscriber: Callable[[], None] | None = None
    parser_status: str | None = None
    audio_url: str | None = None
    eom_utc: str | None = None
    active_alert: bool = False
    alert: dict[str, Any] = field(default_factory=dict)
    test_effective_severity: int = DEFAULT_TEST_EFFECTIVE_SEVERITY

    @property
    def topic_status(self) -> str:
        return f"{self.topic_root}/{TOPIC_STATUS}"

    @property
    def topic_audio_url(self) -> str:
        return f"{self.topic_root}/{TOPIC_AUDIO_URL}"

    @property
    def topic_same_alert(self) -> str:
        return f"{self.topic_root}/{TOPIC_SAME_ALERT}"

    @property
    def topic_eom(self) -> str:
        return f"{self.topic_root}/{TOPIC_EOM}"

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a listener for entity updates."""
        self.listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in self.listeners:
                self.listeners.remove(listener)

        return remove_listener

    @callback
    def async_notify(self) -> None:
        """Notify entities that state changed."""
        for listener in list(self.listeners):
            listener()

    async def async_start(self) -> None:
        """Subscribe to MQTT topics."""
        self.unsubscribers.append(
            await mqtt.async_subscribe(self.hass, self.topic_status, self._message_status)
        )
        self.unsubscribers.append(
            await mqtt.async_subscribe(
                self.hass, self.topic_audio_url, self._message_audio_url
            )
        )
        self.unsubscribers.append(
            await mqtt.async_subscribe(
                self.hass, self.topic_same_alert, self._message_same_alert
            )
        )
        self.unsubscribers.append(
            await mqtt.async_subscribe(self.hass, self.topic_eom, self._message_eom)
        )

    async def async_stop(self) -> None:
        """Unsubscribe from MQTT topics."""
        if self.expiry_unsubscriber:
            self.expiry_unsubscriber()
            self.expiry_unsubscriber = None
        for unsub in self.unsubscribers:
            unsub()
        self.unsubscribers.clear()
        self.listeners.clear()

    @callback
    def _message_status(self, msg: mqtt.ReceiveMessage) -> None:
        self.parser_status = msg.payload
        self.async_notify()

    @callback
    def _message_audio_url(self, msg: mqtt.ReceiveMessage) -> None:
        self.audio_url = msg.payload
        self.async_notify()

    @callback
    def _message_same_alert(self, msg: mqtt.ReceiveMessage) -> None:
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            _LOGGER.warning("Ignoring invalid NWR alert JSON on %s", msg.topic)
            return

        event_code = str(payload.get("event_code", "")).upper()
        severity = TIER_BY_CODE.get(event_code, 4)
        effective_severity = severity
        if severity == 5:
            effective_severity = self.test_effective_severity
        event_name = EVENT_NAMES.get(event_code, f"Unknown Alert ({event_code})")
        counties = payload.get("counties") or []
        county_codes = ", ".join(str(county) for county in counties)

        self.alert = {
            **payload,
            ATTR_EVENT_CODE: event_code,
            ATTR_EVENT_NAME: event_name,
            ATTR_SEVERITY: severity,
            ATTR_SEVERITY_LABEL: SEVERITY_LABELS.get(severity, "Advisory"),
            ATTR_EFFECTIVE_SEVERITY: effective_severity,
            ATTR_EFFECTIVE_SEVERITY_LABEL: SEVERITY_LABELS.get(
                effective_severity, "Advisory"
            ),
            ATTR_COUNTIES: counties,
            ATTR_COUNTY_CODES: county_codes,
            ATTR_ISSUE_UTC: payload.get("issue_utc"),
            ATTR_EXPIRY_UTC: payload.get("issue_expiry_utc"),
            ATTR_REMAINING_SECONDS: payload.get("true_remaining_secs"),
            ATTR_RAW: payload.get("raw"),
        }
        self.active_alert = True
        self._schedule_expiry(self.alert.get(ATTR_EXPIRY_UTC))
        self.hass.bus.async_fire(EVENT_ALERT_RECEIVED, self.alert)
        self.async_notify()

    @callback
    def _message_eom(self, msg: mqtt.ReceiveMessage) -> None:
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            payload = {"eom_utc": msg.payload}

        self.eom_utc = payload.get("eom_utc")
        self.hass.bus.async_fire(EVENT_EOM_RECEIVED, payload)
        self.async_notify()

    @callback
    def _schedule_expiry(self, expiry_utc: str | None) -> None:
        if self.expiry_unsubscriber:
            self.expiry_unsubscriber()
            self.expiry_unsubscriber = None
        if not expiry_utc:
            return
        expiry_dt = dt_util.parse_datetime(expiry_utc)
        if not expiry_dt:
            return
        expiry_dt = dt_util.as_utc(expiry_dt)
        if expiry_dt <= dt_util.utcnow():
            self._expire_alert()
            return
        self.expiry_unsubscriber = event_helper.async_track_point_in_utc_time(
            self.hass, self._expire_alert, expiry_dt
        )

    @callback
    def _expire_alert(self, *_: Any) -> None:
        expired = dict(self.alert)
        self.active_alert = False
        self.alert = {}
        self.expiry_unsubscriber = None
        self.hass.bus.async_fire(EVENT_ALERT_EXPIRED, expired)
        self.async_notify()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA-NWR-SDR from a config entry."""
    topic_root = entry.data.get(CONF_TOPIC_ROOT, DEFAULT_TOPIC_ROOT)
    test_effective_severity = entry.options.get(
        CONF_TEST_EFFECTIVE_SEVERITY,
        entry.data.get(CONF_TEST_EFFECTIVE_SEVERITY, DEFAULT_TEST_EFFECTIVE_SEVERITY),
    )
    runtime = NwrSdrRuntime(
        hass=hass,
        entry=entry,
        topic_root=topic_root,
        test_effective_severity=int(test_effective_severity),
    )
    await runtime.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload HA-NWR-SDR."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime: NwrSdrRuntime = hass.data[DOMAIN].pop(entry.entry_id)
        await runtime.async_stop()
    return unload_ok
