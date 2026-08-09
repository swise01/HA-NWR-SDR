# Changelog

## 4.0.0 - 2026-08-09

### Linux and Raspberry Pi hosts

- Add a repeatable installer for Debian, Ubuntu, and Raspberry Pi OS on x86_64 and ARM.
- Install native dependencies, an isolated Python environment, the unprivileged service account, systemd unit, and RTL-SDR driver policy.
- Preserve `config.env` during updates and avoid starting fresh installations with example credentials.
- Add `nwrctl` for dependency/configuration checks, status, logs, editing, and service lifecycle control.
- Expand CI shell validation to cover the installer and management CLI.

## 3.0.0 - 2026-08-09

### Home Assistant

- Prevent retained SAME/EOM messages and duplicate headers from replaying automation events.
- Reject expired, malformed, and structurally invalid payloads.
- Add the complete operational NWR-SAME code set and correct Local Area Emergency to `LAE`.
- Treat unknown valid codes conservatively as warnings instead of advisories.
- Reload automatically after topic-root or test-severity option changes.
- Add timestamp entities, device grouping, translations, and redacted diagnostics.
- Fix current Home Assistant dataclass compatibility with keyword-only entity descriptions.

### Parser and service

- Detect failed SDR/decoder processes, capture useful stderr, and restart the whole pipeline cleanly.
- Publish alerts and status with QoS 1; stop retaining EOM events; clear retained SAME state at expiry.
- Add PPM correction, unique MQTT client IDs, optional TLS, and explicit audio advertisement settings.
- Replace hardcoded Raspberry Pi paths and global process kills with an unprivileged `nwr` account and systemd control-group cleanup.
- Add MQTT/dependency startup checks and service hardening.

### Project

- Make the custom integration the only supported Home Assistant interface and remove the unreliable legacy YAML bridge.
- Add automated tests, HACS validation, hassfest, compile checks, and shellcheck.

## 2.0.0 - 2026-08-08

- Initial HACS integration and split Linux parser/MQTT architecture.
