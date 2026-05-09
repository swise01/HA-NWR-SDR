# HACS Integration

The `nwr_sdr` integration is the common Home Assistant layer for both parser sources:

- Raspberry Pi parser over MQTT
- future HAOS NWR SDR add-on

Both sources must publish the same normalized MQTT schema. The integration turns that schema into consistent Home Assistant entities and events.

## Entities

The integration creates:

- `binary_sensor.nwr_alert_active`
- parser status sensor
- audio URL sensor
- event code sensor
- event name sensor
- SAME severity sensor
- SAME severity label sensor
- effective severity sensor
- effective severity label sensor
- county code sensor
- expiry sensor
- EOM timestamp sensor

## Events

The integration fires:

```text
nwr_same_alert_received
nwr_eom_received
nwr_alert_expired
```

Example automation:

```yaml
trigger:
  - platform: event
    event_type: nwr_same_alert_received
condition:
  - condition: template
    value_template: "{{ trigger.event.data.effective_severity | int <= 2 }}"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "NWR {{ trigger.event.data.event_name }}"
      message: "{{ trigger.event.data.county_codes }}"
```

## SAME Severity vs Effective Severity

The integration keeps two severity concepts:

- `severity`: the actual SAME tier from the event code
- `effective_severity`: the tier users want automations to treat it as

Required Weekly Test (`RWT`) and Required Monthly Test (`RMT`) always remain labeled as tests with actual tier 5.

The options flow includes a slider for test effective severity:

- `5`: tests behave like low-priority test events
- `1`: tests propagate through automations like imminent-threat events

This lets users verify the full alert path during weekly tests without pretending the event is not a test.

## MQTT Contract

Default topic root:

```text
nwr
```

Topics:

```text
nwr/status
nwr/audio/url
nwr/alert/same
nwr/alert/eom
```

The Pi parser and HAOS add-on should both publish this same contract.
