"""Validation helpers for NWR radio controls."""

from __future__ import annotations

import json
import math
from typing import Any

NOAA_FREQUENCIES = (
    "162.400M",
    "162.425M",
    "162.450M",
    "162.475M",
    "162.500M",
    "162.525M",
    "162.550M",
)
GAIN_MIN = 0.0
GAIN_MAX = 50.0
GAIN_STEP = 0.1
PPM_MIN = -100
PPM_MAX = 100


def normalize_frequency(value: Any) -> str:
    """Return an allow-listed NOAA Weather Radio frequency."""
    frequency = str(value).strip().upper()
    if frequency not in NOAA_FREQUENCIES:
        raise ValueError("frequency must be a NOAA Weather Radio channel")
    return frequency


def normalize_gain(value: Any) -> float:
    """Return a bounded tuner gain."""
    if isinstance(value, bool):
        raise ValueError("gain must be numeric")
    try:
        gain = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("gain must be numeric") from exc
    if not math.isfinite(gain) or not GAIN_MIN <= gain <= GAIN_MAX:
        raise ValueError(f"gain must be between {GAIN_MIN} and {GAIN_MAX}")
    return round(gain, 1)


def normalize_ppm(value: Any) -> int:
    """Return a bounded integer PPM correction."""
    if isinstance(value, bool):
        raise ValueError("PPM must be an integer")
    try:
        ppm_number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("PPM must be an integer") from exc
    if not math.isfinite(ppm_number) or not ppm_number.is_integer():
        raise ValueError("PPM must be an integer")
    ppm = int(ppm_number)
    if not PPM_MIN <= ppm <= PPM_MAX:
        raise ValueError(f"PPM must be between {PPM_MIN} and {PPM_MAX}")
    return ppm


def normalize_control_state(payload: str | bytes) -> dict[str, Any]:
    """Validate a retained parser control-state payload."""
    try:
        state = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("control state must be valid JSON") from exc
    if not isinstance(state, dict):
        raise ValueError("control state must be an object")
    return {
        **state,
        "frequency": normalize_frequency(state.get("frequency")),
        "gain": normalize_gain(state.get("gain")),
        "ppm": normalize_ppm(state.get("ppm")),
    }
