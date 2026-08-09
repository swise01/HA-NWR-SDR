"""Tests for bounded Home Assistant radio controls."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.nwr_sdr import NwrSdrRuntime
from custom_components.nwr_sdr.control import (
    normalize_control_state,
    normalize_frequency,
    normalize_gain,
    normalize_ppm,
)


@pytest.mark.parametrize(
    ("normalizer", "value"),
    [
        (normalize_frequency, "162.575M"),
        (normalize_gain, 50.1),
        (normalize_gain, float("nan")),
        (normalize_gain, True),
        (normalize_ppm, 1.5),
        (normalize_ppm, -101),
        (normalize_ppm, False),
    ],
)
def test_control_values_are_bounded(normalizer, value) -> None:
    with pytest.raises(ValueError):
        normalizer(value)


def test_control_state_is_normalized() -> None:
    state = normalize_control_state(
        json.dumps({"frequency": " 162.400m ", "gain": "28.04", "ppm": "3"})
    )
    assert state["frequency"] == "162.400M"
    assert state["gain"] == 28.0
    assert state["ppm"] == 3


def test_runtime_publishes_nonretained_allow_listed_command() -> None:
    runtime = NwrSdrRuntime(hass=Mock(), entry=Mock(), topic_root="nwr")
    with patch(
        "custom_components.nwr_sdr.mqtt.async_publish", new=AsyncMock()
    ) as publish:
        request_id = asyncio.run(runtime.async_send_control("set_gain", 31.2))

    payload = json.loads(publish.await_args.args[2])
    assert publish.await_args.args[1] == "nwr/control/command"
    assert payload == {
        "command": "set_gain",
        "request_id": request_id,
        "value": 31.2,
    }
    assert publish.await_args.kwargs == {"qos": 1, "retain": False}


def test_runtime_ignores_invalid_control_state() -> None:
    runtime = NwrSdrRuntime(hass=Mock(), entry=Mock(), topic_root="nwr")
    runtime._message_control_state(
        SimpleNamespace(topic="nwr/control/state", payload='{"gain":99}')
    )
    assert runtime.control_state == {}
