# Configuration guide

The host installer writes the protected runtime configuration to `/opt/nwr/config.env`. Use `sudo nwrctl edit` to change it and `sudo nwrctl check` to validate dependencies, Python packages, the MQTT connection, and service state without displaying the MQTT password.

## Radio

Set `SDR_FREQUENCY` to the local NOAA Weather Radio transmitter. The seven channels span `162.400M` through `162.550M` in 25 kHz increments.

Use a receiver serial in `SDR_DEVICE_INDEX` when multiple RTL-SDRs are attached. Start with moderate gain and adjust antenna placement before using maximum gain. Set `SDR_PPM` only after measuring the receiver's frequency error.

## County filtering

`FIPS_FILTER` is a comma-separated list of six-digit SAME location codes:

```text
0 + two-digit state FIPS + three-digit county FIPS
```

Leave it empty to publish all successfully decoded alerts.

## MQTT

Configure `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS`, and `MQTT_TOPIC_ROOT`. Each parser must have a unique `MQTT_CLIENT_ID`; the default example is suitable for only one parser.

For a TLS broker:

```env
MQTT_TLS=true
MQTT_CA_CERT=/etc/ssl/certs/ca-certificates.crt
```

The parser publishes alert and status messages with QoS 1. SAME state is retained only until its expiry. EOM is an edge event and is never retained.

## Audio URL

The parser normally discovers the LAN address used to reach the MQTT broker. Override it when required:

```env
AUDIO_ADVERTISE_HOST=nwr-radio.example.lan
```

Or publish a complete reverse-proxy URL:

```env
AUDIO_STREAM_URL=https://nwr-radio.example.com/nwr.mp3
```

The built-in server listens on all interfaces and has no authentication. Restrict it with firewall policy or an authenticated reverse proxy before exposing it beyond the LAN.

## Logging

Leave `LOG_FILE` empty to use `journalctl -u nwr.service`. To keep a separate file, create a directory writable by `nwr`, set the path in `config.env`, and adapt `pi/logrotate-nwr` if needed.

## Home Assistant

The integration's options allow both the MQTT topic root and effective test severity to be changed. Saving options automatically reloads the config entry.

Use `nwr_same_alert_received` for new alerts. Retained state restores entities after Home Assistant restarts but deliberately does not fire that event again.
