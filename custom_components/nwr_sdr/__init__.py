"""HA-NWR-SDR integration."""

from __future__ import annotations

import json
import logging
import uuid
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
    ATTR_EXPIRY_UTC,
    CONF_TEST_EFFECTIVE_SEVERITY,
    CONF_TOPIC_ROOT,
    DEFAULT_TEST_EFFECTIVE_SEVERITY,
    DEFAULT_TOPIC_ROOT,
    DOMAIN,
    EVENT_ALERT_EXPIRED,
    EVENT_ALERT_RECEIVED,
    EVENT_EOM_RECEIVED,
    TOPIC_AUDIO_URL,
    TOPIC_CONTROL_COMMAND,
    TOPIC_CONTROL_STATE,
    TOPIC_EOM,
    TOPIC_SAME_ALERT,
    TOPIC_STATUS,
)
from .control import (
    normalize_control_state,
    normalize_frequency,
    normalize_gain,
    normalize_ppm,
)
from .payload import (
    alert_identity,
    normalize_alert_payload,
    normalize_topic_root,
    parse_utc,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]


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
    last_alert_id: str | None = None
    last_eom_id: str | None = None
    control_state: dict[str, Any] = field(default_factory=dict)

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

    @property
    def topic_control_command(self) -> str:
        return f"{self.topic_root}/{TOPIC_CONTROL_COMMAND}"

    @property
    def topic_control_state(self) -> str:
        return f"{self.topic_root}/{TOPIC_CONTROL_STATE}"

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
        self.unsubscribers.append(
            await mqtt.async_subscribe(
                self.hass, self.topic_control_state, self._message_control_state
            )
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
        if not msg.payload:
            return
        try:
            alert = normalize_alert_payload(
                msg.payload, self.test_effective_severity
            )
        except ValueError as exc:
            _LOGGER.warning("Ignoring NWR alert on %s: %s", msg.topic, exc)
            return

        message_id = alert_identity(alert)
        is_replay = bool(getattr(msg, "retain", False))
        is_duplicate = message_id == self.last_alert_id
        self.alert = alert
        self.active_alert = True
        self.last_alert_id = message_id
        self._schedule_expiry(self.alert.get(ATTR_EXPIRY_UTC))
        if not is_replay and not is_duplicate:
            self.hass.bus.async_fire(EVENT_ALERT_RECEIVED, self.alert)
        self.async_notify()

    @callback
    def _message_eom(self, msg: mqtt.ReceiveMessage) -> None:
        if not msg.payload:
            return
        try:
            payload = json.loads(msg.payload)
        except (json.JSONDecodeError, TypeError):
            payload = {"eom_utc": msg.payload}
        if not isinstance(payload, dict):
            _LOGGER.warning("Ignoring invalid NWR EOM payload on %s", msg.topic)
            return
        eom_dt = parse_utc(payload.get("eom_utc"))
        if eom_dt is None:
            _LOGGER.warning("Ignoring invalid NWR EOM timestamp on %s", msg.topic)
            return
        eom_id = eom_dt.isoformat()
        is_replay = bool(getattr(msg, "retain", False))
        is_duplicate = eom_id == self.last_eom_id
        self.eom_utc = eom_id
        self.last_eom_id = eom_id
        if not is_replay and not is_duplicate:
            self.hass.bus.async_fire(EVENT_EOM_RECEIVED, {"eom_utc": eom_id})
        self.async_notify()

    @callback
    def _message_control_state(self, msg: mqtt.ReceiveMessage) -> None:
        if not msg.payload:
            return
        try:
            self.control_state = normalize_control_state(msg.payload)
        except ValueError as exc:
            _LOGGER.warning("Ignoring NWR control state on %s: %s", msg.topic, exc)
            return
        self.async_notify()

    async def async_send_control(self, command: str, value: Any = None) -> str:
        """Publish one allow-listed radio control command."""
        if command == "set_frequency":
            value = normalize_frequency(value)
        elif command == "set_gain":
            value = normalize_gain(value)
        elif command == "set_ppm":
            value = normalize_ppm(value)
        elif command != "restart" or value is not None:
            raise ValueError("unsupported radio control command")
        payload: dict[str, Any] = {
            "command": command,
            "request_id": uuid.uuid4().hex,
        }
        if value is not None:
            payload["value"] = value
        await mqtt.async_publish(
            self.hass,
            self.topic_control_command,
            json.dumps(payload, separators=(",", ":")),
            qos=1,
            retain=False,
        )
        return payload["request_id"]

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
        if not self.active_alert:
            return
        expired = dict(self.alert)
        self.active_alert = False
        self.alert = {}
        self.expiry_unsubscriber = None
        self.hass.bus.async_fire(EVENT_ALERT_EXPIRED, expired)
        self.async_notify()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA-NWR-SDR from a config entry."""
    topic_root = normalize_topic_root(
        entry.options.get(
            CONF_TOPIC_ROOT,
            entry.data.get(CONF_TOPIC_ROOT, DEFAULT_TOPIC_ROOT),
        )
    )
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
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration after its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload HA-NWR-SDR."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime: NwrSdrRuntime = hass.data[DOMAIN].pop(entry.entry_id)
        await runtime.async_stop()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok
