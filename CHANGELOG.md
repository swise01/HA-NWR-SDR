# Changelog

## 2.0.0 - Unreleased

### Added

- HACS-compatible `nwr_sdr` custom integration.
- Config flow for MQTT topic root and test effective severity.
- Common Home Assistant entities for parser status, audio URL, alert state, event code/name, SAME severity, effective severity, county codes, expiry, and EOM time.
- Standard Home Assistant events:
  - `nwr_same_alert_received`
  - `nwr_eom_received`
  - `nwr_alert_expired`
- Separate actual SAME severity from effective automation severity.
- Slider option to let tests remain tier 5/Test while propagating as a stronger effective severity.
- Hardened Raspberry Pi parser with raw and filtered SAME decoder paths.
- Parser-side duplicate SAME/EOM suppression.
- NWS-issued expiry calculation from SAME issue time plus valid duration.
- Parser file logging and MQTT audit logging.
- Logrotate config for parser and MQTT logs.

### Changed

- v2 MQTT alert topic is `nwr/alert/same`.
- v2 EOM topic is `nwr/alert/eom`.
- Public Home Assistant YAML package is now an event bridge/example, not the primary integration path.
- User-specific alert actions are intentionally left to user automations.

### Planned

- Separate Home Assistant OS add-on repository for direct SDR-on-HAOS installs.
- Shared schema compatibility between the Pi parser and HAOS add-on.
