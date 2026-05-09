# HA-NWR-SDR v2

NOAA Weather Radio alerting for Home Assistant using an RTL-SDR on a Raspberry Pi and MQTT.

v2 is focused on the architecture that is reliable today:

```text
RTL-SDR -> Raspberry Pi parser -> MQTT -> HACS integration
```

The parser decodes SAME/EAS headers from local NOAA Weather Radio, publishes structured alert JSON to MQTT, hosts a live MP3 stream, and keeps enough local logs to debug missed weekly tests after the fact. The Home Assistant integration consumes that same MQTT contract whether the publisher is the Pi parser or a future HAOS add-on.

## Status

Supported now:

- Split Raspberry Pi plus Home Assistant over MQTT
- RTL-SDR radio decode with `rtl_fm`, `ffmpeg`, and `multimon-ng`
- Dual SAME decode paths: raw audio and filtered audio
- Duplicate SAME/EOM suppression
- NWS-issued expiry timestamps from SAME `JJJHHMM + valid duration`
- Retained MQTT state for HA startup recovery
- 30-day parser logs
- 10-day MQTT event audit logs for `nwr/#`
- HACS integration with common entities and events
- Separate actual SAME severity and effective automation severity

Planned separately:

- Home Assistant OS add-on that runs the SDR/parser directly beside HA

HACS alone is not the right place to run `rtl_fm`, claim USB SDR hardware, or manage long-running decoder processes. A direct HAOS install should be a Supervisor add-on. The HACS integration is the common Home Assistant layer for both sources.

## MQTT Topics

The v2 parser publishes:

| Topic | Retain | Payload |
|---|---:|---|
| `nwr/status` | yes | `running`, `offline`, or `error` |
| `nwr/audio/url` | yes | HTTP MP3 stream URL |
| `nwr/alert/same` | yes | SAME alert JSON |
| `nwr/alert/eom` | yes | EOM JSON |

SAME alert JSON includes:

- `event_code`
- `org`
- `counties`
- `wfo`
- `valid_hours`
- `valid_mins`
- `valid_seconds`
- `issue_utc`
- `issue_expiry_utc`
- `true_remaining_secs`
- `received_utc`
- `raw`

## Install: Raspberry Pi Parser

Install OS packages:

```bash
sudo apt-get update
sudo apt-get install -y rtl-sdr multimon-ng ffmpeg python3-venv python3-pip mosquitto-clients logrotate
```

Prevent the Linux DVB driver from claiming the RTL-SDR:

```bash
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl.conf
sudo usermod -aG plugdev "$USER"
sudo reboot
```

Install the parser:

```bash
sudo mkdir -p /opt/nwr
sudo chown "$USER:$USER" /opt/nwr
python3 -m venv /opt/nwr_venv
/opt/nwr_venv/bin/pip install -r pi/requirements.txt
cp pi/nwr_parser.py pi/nwr-mqtt-audit.sh /opt/nwr/
cp pi/config.env.example /opt/nwr/config.env
chmod +x /opt/nwr/nwr_parser.py /opt/nwr/nwr-mqtt-audit.sh
```

Edit `/opt/nwr/config.env` for your MQTT broker, SDR serial/index, NWR frequency, and county FIPS filter.

Install services and log rotation:

```bash
sudo cp pi/nwr_parser.service /etc/systemd/system/nwr.service
sudo cp pi/nwr-mqtt-audit.service /etc/systemd/system/
sudo cp pi/logrotate-nwr /etc/logrotate.d/nwr
sudo systemctl daemon-reload
sudo systemctl enable --now nwr.service nwr-mqtt-audit.service
```

Check live state:

```bash
systemctl status nwr.service nwr-mqtt-audit.service
journalctl -u nwr.service -f
tail -f /home/$USER/logs/nwr/parser.log
tail -f /home/$USER/logs/mqtt/pi-mqtt.log
```

## Install: Home Assistant Integration

Install this repository as a custom HACS integration:

1. HACS -> Integrations -> three-dot menu -> Custom repositories.
2. Repository: `https://github.com/swise01/HA-NWR-SDR`
3. Category: Integration
4. Install **HA-NWR-SDR**.
5. Restart Home Assistant.
6. Add **HA-NWR-SDR** from Home Assistant **Settings -> Devices & services**.

Configuration:

- `topic_root`: default `nwr`
- `test_effective_severity`: slider from 1 to 5

Required Weekly Test and Required Monthly Test events always remain labeled as tests with actual SAME tier 5. The effective severity slider only controls how strongly tests propagate to automations. Set it to 1 when you want weekly tests to exercise the same automations as imminent-threat alerts.

The integration creates common entities and fires:

```text
nwr_same_alert_received
nwr_eom_received
nwr_alert_expired
```

Automate from those events however you want. This project does not assume you have any particular phone, speaker, relay board, alarm, or lighting setup.

## Optional: YAML Bridge Package

`homeassistant/packages/nwr.yaml` is a temporary bridge/example for users who do not want to install the custom integration yet. It follows the same event-first design.

Do not install both the HACS integration and the YAML bridge package at the same time unless you intentionally want duplicate entities/events.

```yaml
homeassistant:
  packages:
    nwr: !include packages/nwr.yaml
```

Edit only the NWS zone placeholders, or remove the `rest:` block if you only want SAME/MQTT data.

Restart Home Assistant after editing.

## Weekly Test Debugging

Most NWR weekly tests happen only once or twice per week, so v2 keeps durable logs:

- Parser decode logs: `/home/<user>/logs/nwr/parser.log`
- MQTT event audit: `/home/<user>/logs/mqtt/pi-mqtt.log`

When a test fails, check the parser log first:

- `multimon[raw]: ... ZCZC...` means the raw path decoded the header.
- `multimon[filtered]: ... ZCZC...` means the filtered path decoded the header.
- `EOM received` without a preceding `ZCZC` means the radio decoder heard the end marker but missed the header.
- A line in `pi-mqtt.log` under `nwr/alert/same` means HA received an MQTT event to process.

## HAOS Direct SDR

Direct HAOS SDR support should be built as a Home Assistant add-on, not just HACS.

Reason:

- HACS custom integrations run inside Home Assistant Core.
- SDR decoding needs USB hardware access, native packages, long-running child processes, and log rotation.
- Supervisor add-ons are designed for that boundary.

The likely future shape is:

```text
HAOS add-on: rtl_fm + ffmpeg + multimon-ng + parser
HACS integration: common entities, events, setup flow, diagnostics, repairs
YAML/dashboard: optional examples only
```

For now, the split Pi architecture is the supported v2 path.
