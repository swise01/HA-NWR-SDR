# v2 Architecture Notes

This project should split into three clean layers.

## 1. HA-NWR-SDR

This original repo remains the supported Raspberry Pi plus MQTT version.

Responsibilities:

- Install and run the Pi SDR parser.
- Decode SAME/EAS with `rtl_fm`, `ffmpeg`, and `multimon-ng`.
- Publish normalized MQTT events.
- Host the live NWR MP3 stream.
- Provide Pi systemd services and logrotate.
- Document setup, tuning, FIPS/SAME codes, and troubleshooting.

This path should be stable, simple, and easy to debug from logs.

## 2. HAOS NWR SDR Add-on

This should be a new Home Assistant add-on repository so HAOS users can plug an RTL-SDR directly into the HAOS machine.

Responsibilities:

- Own USB SDR access from an add-on container.
- Package native dependencies: `rtl_fm`, `ffmpeg`, `multimon-ng`, Python parser dependencies.
- Expose add-on config for:
  - WX channel/frequency
  - SDR device/index/serial
  - gain
  - sample rate
  - SAME sample rate
  - FIPS/SAME county codes
  - audio stream port
  - MQTT settings or Supervisor service discovery
  - logging level/retention
- Publish the same normalized event schema as the Pi parser.

The add-on should not invent different Home Assistant entities. It should emit the same data contract as the Pi parser.

## 3. HACS Integration

The HACS custom integration is now part of v2 and should become the common Home Assistant layer for both parser sources.

Responsibilities:

- Subscribe to the normalized NWR event stream.
- Create the same entities regardless of source:
  - parser status
  - last SAME event
  - active alert/alarm state
  - event code/name/severity
  - county/FIPS matches
  - expiry/remaining time
  - audio stream URL
  - EOM received
  - diagnostics/last decode source
- Provide config flow/options flow for HA-side behavior:
  - MQTT topic root
  - test effective severity
  - future county display names
  - future NWS zone fallback
- Work with either:
  - Pi parser over MQTT
  - HAOS add-on publishing the same schema

The final user path should be the same inside Home Assistant no matter where the SDR parser runs.

The integration must keep actual SAME severity separate from effective propagation severity. For example, RWT remains a tier 5 test, but the user can set its effective severity to tier 1 to verify full alert automations.

## Current Debugging Hypothesis

The 2026-05-09 Saturday test produced EOM logs but no SAME header. That means the decoder heard the message end marker but missed the header.

Likely tuning areas:

- Gain is already high in the homelab config (`49.6`), so more gain may not help and can overload the dongle.
- Better tests are gain sweep and filter comparison, not simply max gain.
- The v2 parser now runs both raw and filtered SAME decode paths so the next weekly test should show which path catches `ZCZC`.
- Tightening bandwidth/filtering may help header decode, but if too tight it may distort SAME tones. Keep both raw and filtered paths until logs prove one is better.

Use the new logs for the next Wednesday/Saturday test:

- `/home/<parser-user>/logs/nwr/parser.log`
- `/home/<parser-user>/logs/mqtt/pi-mqtt.log`

If the next test shows only `NNNN`, focus on SDR signal quality, antenna placement, gain sweep, and `rtl_fm` demod settings.
If it shows `ZCZC` in parser logs but no HA alert, focus on MQTT and HA integration logic.
