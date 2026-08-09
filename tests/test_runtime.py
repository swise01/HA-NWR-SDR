"""Tests for edge-triggered Home Assistant events."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.nwr_sdr import NwrSdrRuntime
from custom_components.nwr_sdr.const import EVENT_ALERT_RECEIVED, EVENT_EOM_RECEIVED


def _runtime() -> NwrSdrRuntime:
    hass = Mock()
    hass.bus.async_fire = Mock()
    runtime = NwrSdrRuntime(hass=hass, entry=Mock(), topic_root="nwr")
    runtime._schedule_expiry = Mock()
    return runtime


def _alert_message(*, retain: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        topic="nwr/alert/same",
        retain=retain,
        payload=json.dumps(
            {
                "event_code": "TOR",
                "counties": ["018157"],
                "issue_utc": "2099-01-01T00:00:00+00:00",
                "issue_expiry_utc": "2099-01-01T01:00:00+00:00",
                "received_utc": "2099-01-01T00:01:00+00:00",
                "raw": "ZCZC-WXR-TOR-018157+0100-0010000-KIND/NWS-",
            }
        ),
    )


def test_retained_alert_restores_state_without_event() -> None:
    runtime = _runtime()
    runtime._message_same_alert(_alert_message(retain=True))
    assert runtime.active_alert
    runtime.hass.bus.async_fire.assert_not_called()


def test_duplicate_alert_only_fires_once() -> None:
    runtime = _runtime()
    runtime._message_same_alert(_alert_message())
    runtime._message_same_alert(_alert_message())
    runtime.hass.bus.async_fire.assert_called_once()
    assert runtime.hass.bus.async_fire.call_args.args[0] == EVENT_ALERT_RECEIVED


def test_retained_alert_clear_is_silent() -> None:
    runtime = _runtime()
    runtime._message_same_alert(
        SimpleNamespace(topic="nwr/alert/same", retain=False, payload="")
    )
    assert not runtime.active_alert
    runtime.hass.bus.async_fire.assert_not_called()


def test_retained_eom_does_not_replay_event() -> None:
    runtime = _runtime()
    runtime._message_eom(
        SimpleNamespace(
            topic="nwr/alert/eom",
            retain=True,
            payload=json.dumps({"eom_utc": "2099-01-01T00:02:00+00:00"}),
        )
    )
    runtime.hass.bus.async_fire.assert_not_called()


def test_new_eom_fires_event_once() -> None:
    runtime = _runtime()
    message = SimpleNamespace(
        topic="nwr/alert/eom",
        retain=False,
        payload=json.dumps({"eom_utc": "2099-01-01T00:02:00+00:00"}),
    )
    runtime._message_eom(message)
    runtime._message_eom(message)
    runtime.hass.bus.async_fire.assert_called_once_with(
        EVENT_EOM_RECEIVED, {"eom_utc": "2099-01-01T00:02:00+00:00"}
    )
