"""Tests for NWR payload validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from custom_components.nwr_sdr.const import EVENT_NAMES, TIER_BY_CODE
from custom_components.nwr_sdr.payload import (
    alert_identity,
    normalize_alert_payload,
    normalize_topic_root,
)

NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


def _payload(**overrides: object) -> str:
    payload = {
        "event_code": "TOR",
        "counties": ["018157"],
        "issue_utc": "2026-08-09T00:00:00+00:00",
        "issue_expiry_utc": "2026-08-09T01:00:00+00:00",
        "received_utc": "2026-08-09T00:05:00+00:00",
        "raw": "ZCZC-WXR-TOR-018157+0100-2210000-KIND/NWS-",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_normalize_topic_root() -> None:
    assert normalize_topic_root(" /school/nwr/ ") == "school/nwr"
    for invalid in ("", "/", "nwr/#", "nwr/+", "nwr//alerts"):
        with pytest.raises(ValueError):
            normalize_topic_root(invalid)


def test_normalize_alert_payload() -> None:
    alert = normalize_alert_payload(_payload(), 5, now=NOW)
    assert alert["event_name"] == "Tornado Warning"
    assert alert["severity"] == 1
    assert alert["county_codes"] == "018157"
    assert alert["true_remaining_secs"] == 3600
    assert alert_identity(alert).startswith("ZCZC-WXR-TOR")


def test_unknown_code_is_conservative() -> None:
    alert = normalize_alert_payload(_payload(event_code="XYZ"), 5, now=NOW)
    assert alert["severity"] == 2
    assert alert["event_name"] == "Unknown Alert (XYZ)"


@pytest.mark.parametrize(
    "payload",
    (
        "[]",
        "not-json",
        _payload(event_code=""),
        _payload(counties="018157"),
        _payload(issue_expiry_utc="2026-08-08T23:59:00+00:00"),
    ),
)
def test_invalid_alerts_are_rejected(payload: str) -> None:
    with pytest.raises(ValueError):
        normalize_alert_payload(payload, 5, now=NOW)


def test_official_v3_codes_have_names_and_tiers() -> None:
    codes = {"CFA", "CFW", "SVS", "SQW", "SSA", "SSW", "TRA", "TRW", "BLU", "CAE", "LAE", "TOE"}
    assert codes <= EVENT_NAMES.keys()
    assert codes <= TIER_BY_CODE.keys()
