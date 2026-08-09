"""Diagnostics support for HA-NWR-SDR."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import NwrSdrRuntime
from .const import ATTR_RAW, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics without raw SAME headers or network URLs."""
    runtime: NwrSdrRuntime = hass.data[DOMAIN][entry.entry_id]
    alert = {key: value for key, value in runtime.alert.items() if key != ATTR_RAW}
    return {
        "entry": {
            "topic_root": runtime.topic_root,
            "test_effective_severity": runtime.test_effective_severity,
        },
        "runtime": {
            "parser_status": runtime.parser_status,
            "active_alert": runtime.active_alert,
            "alert": alert,
            "eom_utc": runtime.eom_utc,
            "audio_url_configured": bool(runtime.audio_url),
        },
    }
