# Home Assistant integration

The `nwr_sdr` integration subscribes to the normalized MQTT contract and groups its entities under one NOAA Weather Radio device.

## Entities

- Alert active safety binary sensor
- Parser status diagnostic enum
- Audio URL diagnostic sensor
- Event code and name
- Actual SAME severity and label
- Effective automation severity and label
- County codes
- Issued, received, expiry, and EOM timestamp sensors

## Events

```text
nwr_same_alert_received
nwr_eom_received
nwr_alert_expired
```

New non-retained messages create received/EOM events. Retained MQTT messages only restore entity state, preventing notification replays after Home Assistant or the integration restarts. Repeated SAME headers with the same identity are also deduplicated.

Expired alerts and malformed JSON are rejected. Unknown but well-formed three-character codes are surfaced as unknown warnings with a conservative tier 2 effective severity.

Diagnostics are available from the integration entry. They omit the raw SAME header and audio URL.
