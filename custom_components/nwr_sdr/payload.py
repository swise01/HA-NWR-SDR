"""Validation and normalization for NWR MQTT payloads."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .const import (
    ATTR_COUNTIES,
    ATTR_COUNTY_CODES,
    ATTR_EFFECTIVE_SEVERITY,
    ATTR_EFFECTIVE_SEVERITY_LABEL,
    ATTR_EVENT_CODE,
    ATTR_EVENT_NAME,
    ATTR_EXPIRY_UTC,
    ATTR_ISSUE_UTC,
    ATTR_RAW,
    ATTR_RECEIVED_UTC,
    ATTR_REMAINING_SECONDS,
    ATTR_SEVERITY,
    ATTR_SEVERITY_LABEL,
    EVENT_NAMES,
    SEVERITY_LABELS,
    TIER_BY_CODE,
)


def normalize_topic_root(value: str) -> str:
    """Return a safe MQTT topic root."""
    topic_root = str(value).strip().strip("/")
    if not topic_root or "//" in topic_root or "+" in topic_root or "#" in topic_root:
        raise ValueError("MQTT topic root must be non-empty and contain no wildcards")
    return topic_root


def parse_utc(value: Any) -> datetime | None:
    """Parse an ISO timestamp and normalize it to UTC."""
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def alert_identity(payload: dict[str, Any]) -> str:
    """Build a stable identity across SAME header rebroadcasts."""
    raw = payload.get(ATTR_RAW)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "|".join(
        (
            str(payload.get(ATTR_EVENT_CODE, "")),
            str(payload.get(ATTR_ISSUE_UTC, "")),
            str(payload.get(ATTR_EXPIRY_UTC, "")),
            str(payload.get(ATTR_COUNTY_CODES, "")),
        )
    )


def normalize_alert_payload(
    raw_payload: str,
    test_effective_severity: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate and normalize one SAME alert payload."""
    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")

    event_code = str(payload.get(ATTR_EVENT_CODE, "")).strip().upper()
    if len(event_code) != 3 or not event_code.isalnum():
        raise ValueError("event_code must be a three-character SAME code")

    counties = payload.get(ATTR_COUNTIES, [])
    if not isinstance(counties, list) or any(
        not isinstance(county, (str, int)) for county in counties
    ):
        raise ValueError("counties must be a JSON list")
    counties = [str(county).strip() for county in counties if str(county).strip()]

    expiry = parse_utc(payload.get(ATTR_EXPIRY_UTC))
    if expiry is None:
        raise ValueError("issue_expiry_utc must be a valid ISO timestamp")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if expiry <= current:
        raise ValueError("alert has already expired")

    severity = TIER_BY_CODE.get(event_code, 2)
    effective_severity = (
        max(1, min(5, int(test_effective_severity))) if severity == 5 else severity
    )
    county_codes = ", ".join(counties)

    return {
        **payload,
        ATTR_EVENT_CODE: event_code,
        ATTR_EVENT_NAME: EVENT_NAMES.get(event_code, f"Unknown Alert ({event_code})"),
        ATTR_SEVERITY: severity,
        ATTR_SEVERITY_LABEL: SEVERITY_LABELS[severity],
        ATTR_EFFECTIVE_SEVERITY: effective_severity,
        ATTR_EFFECTIVE_SEVERITY_LABEL: SEVERITY_LABELS[effective_severity],
        ATTR_COUNTIES: counties,
        ATTR_COUNTY_CODES: county_codes,
        ATTR_ISSUE_UTC: payload.get(ATTR_ISSUE_UTC),
        ATTR_EXPIRY_UTC: expiry.isoformat(),
        ATTR_RECEIVED_UTC: payload.get(ATTR_RECEIVED_UTC),
        ATTR_REMAINING_SECONDS: max(0, int((expiry - current).total_seconds())),
        ATTR_RAW: payload.get(ATTR_RAW),
    }
