# HA-NWR-SDR v4

Local NOAA Weather Radio alerting for Home Assistant using an RTL-SDR, MQTT, and a small Debian-family Linux host.

```text
RTL-SDR -> Linux parser -> MQTT -> Home Assistant integration
```

The parser decodes SAME/EAS headers, publishes validated alert JSON, and hosts a live MP3 stream. The Home Assistant integration restores retained alert state without replaying old automation events.

## v4 highlights

- One-command host installer for Debian, Ubuntu, and Raspberry Pi OS on x86_64 and ARM.
- Safe upgrades that preserve `config.env` and restart only an already configured service.
- `nwrctl` management CLI for checks, status, logs, configuration, and service control.
- Fresh installs remain stopped until MQTT credentials are configured.

## v3 radio and Home Assistant improvements

- Edge-triggered Home Assistant events: retained MQTT state no longer replays notifications after a reload.
- Expired, malformed, and invalid alert payloads are ignored.
- Complete operational NWR-SAME event codes from the National Weather Service.
- Automatic integration reload after topic or test-severity option changes.
- Timestamp entities, device grouping, translations, and downloadable diagnostics.
- Child-process health monitoring and automatic SDR pipeline recovery.
- Configurable PPM correction, MQTT client ID/TLS, and advertised audio URL.
- Dedicated unprivileged `nwr` service account with hardened systemd settings.

## MQTT contract

| Topic | Retain | Payload |
|---|---:|---|
| `nwr/status` | yes | `running`, `offline`, or `error` |
| `nwr/audio/url` | yes | HTTP MP3 stream URL |
| `nwr/alert/same` | until expiry | SAME alert JSON |
| `nwr/alert/eom` | no | EOM timestamp JSON |

SAME JSON includes the event code, originator, county codes, station, issued/received/expiry timestamps, duration, and raw SAME header.

## Install the Linux or Raspberry Pi host

Clone the repository on a Debian, Ubuntu, or Raspberry Pi OS host and run:

```bash
sudo ./install.sh install
sudo nwrctl edit
sudo nwrctl check
sudo nwrctl enable
```

The installer adds the native RTL-SDR, SAME decoder, audio, Python, and MQTT tools; creates the unprivileged `nwr` account; builds an isolated Python environment; installs the systemd service; and prevents the DVB driver from claiming the radio. A reboot is recommended after the first install.

To install a completed configuration and start immediately:

```bash
sudo ./install.sh install --config /path/to/config.env
```

To upgrade from a repository checkout while preserving configuration:

```bash
git pull --ff-only
sudo ./install.sh update
```

Run `nwrctl help` for management commands. `nwrctl check` does not print the MQTT password.

### Manual installation

The automated installer is recommended. These commands document what it installs and are useful for custom layouts.

Install Debian/Raspberry Pi OS packages:

```bash
sudo apt-get update
sudo apt-get install -y rtl-sdr multimon-ng ffmpeg netcat-openbsd python3-venv python3-pip mosquitto-clients
```

Prevent the DVB driver from claiming the receiver and create the service account:

```bash
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl.conf
sudo useradd --system --home-dir /opt/nwr --shell /usr/sbin/nologin nwr 2>/dev/null || true
sudo usermod -aG plugdev nwr
sudo install -d -o nwr -g nwr -m 0750 /opt/nwr
sudo python3 -m venv /opt/nwr_venv
sudo /opt/nwr_venv/bin/pip install -r pi/requirements.txt
```

Install the files:

```bash
sudo install -o root -g nwr -m 0750 pi/nwr_parser.py /opt/nwr/nwr_parser.py
sudo install -o root -g nwr -m 0640 pi/config.env.example /opt/nwr/config.env
sudo install -o root -g root -m 0644 pi/nwr_parser.service /etc/systemd/system/nwr.service
sudoedit /opt/nwr/config.env
sudo systemctl daemon-reload
sudo systemctl enable --now nwr.service
```

`/opt/nwr/config.env` contains the MQTT password and should remain mode `0640` or stricter. Reboot once after blacklisting the DVB driver or adding the service account to `plugdev`.

Check operation:

```bash
systemctl status nwr.service
journalctl -u nwr.service -f
```

The MP3 endpoint has no built-in authentication. Keep it on a trusted LAN or place it behind an authenticated reverse proxy. Set `AUDIO_STREAM_URL` when Home Assistant should use that proxy URL.

## Install the Home Assistant integration

1. In HACS, open **Integrations -> Custom repositories**.
2. Add `https://github.com/swise01/HA-NWR-SDR` as an Integration.
3. Install **HA-NWR-SDR**, restart Home Assistant, and add it from **Settings -> Devices & services**.
4. Confirm the MQTT topic root, normally `nwr`.

The integration creates a single NOAA Weather Radio device and fires:

```text
nwr_same_alert_received
nwr_eom_received
nwr_alert_expired
```

Required Weekly/Monthly Tests remain tier 5/Test. The effective-severity option controls how strongly test events exercise your automations.

## Example automation

```yaml
triggers:
  - trigger: event
    event_type: nwr_same_alert_received
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.effective_severity | int <= 2 }}"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "NWR {{ trigger.event.data.event_name }}"
      message: "{{ trigger.event.data.county_codes }}"
```

The integration intentionally does not assume particular speakers, phones, lights, sirens, or dashboards.

## Documentation

- [Configuration guide](CONFIGURATION.md)
- [Home Assistant integration](docs/integration.md)
- [Audio streaming](docs/audio_streaming.md)
- [v4 architecture](docs/architecture.md)

The old YAML event bridge was removed in v3 because it duplicated integration events and could not reliably model concurrent alerts. Use the custom integration as the supported Home Assistant interface.
