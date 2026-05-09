# Configuration Guide

This guide covers the v2 Raspberry Pi plus MQTT setup.

The Home Assistant package is a bridge layer. It creates common entities and fires Home Assistant events, but it does not assume you have specific speakers, phones, relays, sirens, or dashboards.

## Architecture

```text
RTL-SDR -> Raspberry Pi parser -> MQTT -> Home Assistant bridge package
```

The future target is:

```text
Pi parser or HAOS add-on -> same normalized event schema -> HACS integration -> same HA entities/events
```

## 1. Find Your NWR Station

Use the NOAA station listing to find:

- transmitter callsign
- frequency
- counties served

Common NWR channels:

| Channel | Frequency |
|---|---:|
| WX1 | 162.400 MHz |
| WX2 | 162.425 MHz |
| WX3 | 162.450 MHz |
| WX4 | 162.475 MHz |
| WX5 | 162.500 MHz |
| WX6 | 162.525 MHz |
| WX7 | 162.550 MHz |

## 2. Find SAME/FIPS Codes

The parser can filter SAME alerts by county code.

Format:

```text
0 + 2 digit state FIPS + 3 digit county FIPS
```

Example:

```text
001073
```

Leave `FIPS_FILTER` empty if you want to publish every decoded SAME header.

## 3. Find NWS Zone IDs

The Home Assistant package can also poll the NWS Alerts API.

Zone IDs look like:

```text
ALZ018
ALZ030
```

Replace `YOUR_ZONE_1,YOUR_ZONE_2` in `homeassistant/packages/nwr.yaml`, or remove the `rest:` block if you only want radio/MQTT data.

## 4. Install Pi Dependencies

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

## 5. Install the Parser

```bash
sudo mkdir -p /opt/nwr
sudo chown "$USER:$USER" /opt/nwr

python3 -m venv /opt/nwr_venv
/opt/nwr_venv/bin/pip install -r pi/requirements.txt

cp pi/nwr_parser.py pi/nwr-mqtt-audit.sh /opt/nwr/
cp pi/config.env.example /opt/nwr/config.env
chmod +x /opt/nwr/nwr_parser.py /opt/nwr/nwr-mqtt-audit.sh
```

Edit `/opt/nwr/config.env`:

```env
MQTT_HOST=homeassistant.local
MQTT_PORT=1883
MQTT_USER=mqtt
MQTT_PASS=change-me

SDR_FREQUENCY=162.550M
SDR_DEVICE_INDEX=0
SDR_GAIN=49.6
FIPS_FILTER=
```

For RTL-SDR Blog V4 or serial-numbered dongles, `SDR_DEVICE_INDEX` may be a serial such as `SDRNWR01`.

## 6. Install Services

```bash
sudo cp pi/nwr_parser.service /etc/systemd/system/nwr.service
sudo cp pi/nwr-mqtt-audit.service /etc/systemd/system/
sudo cp pi/logrotate-nwr /etc/logrotate.d/nwr

sudo systemctl daemon-reload
sudo systemctl enable --now nwr.service nwr-mqtt-audit.service
```

Check status:

```bash
systemctl status nwr.service nwr-mqtt-audit.service
journalctl -u nwr.service -f
```

## 7. Install Home Assistant Package

Copy:

```text
homeassistant/packages/nwr.yaml
```

to:

```text
/config/packages/nwr.yaml
```

Enable packages in `configuration.yaml` if needed:

```yaml
homeassistant:
  packages:
    nwr: !include packages/nwr.yaml
```

Restart Home Assistant.

## 8. Build User Automations

The package fires these events:

```text
nwr_same_alert_received
nwr_eom_received
nwr_alert_expired
```

Example automation trigger:

```yaml
trigger:
  - platform: event
    event_type: nwr_same_alert_received
condition:
  - condition: template
    value_template: "{{ trigger.event.data.severity | int <= 2 }}"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "NWR {{ trigger.event.data.event_name }}"
      message: "{{ trigger.event.data.county_codes }}"
```

Users can choose their own phones, speakers, relays, lights, alarms, or dashboards without editing the parser.

## 9. Debugging Weekly Tests

The parser keeps durable logs because weekly tests are hard to chase live:

```bash
tail -f /home/$USER/logs/nwr/parser.log
tail -f /home/$USER/logs/mqtt/pi-mqtt.log
```

Interpretation:

- `multimon[raw]: ... ZCZC...` means the raw decoder caught the SAME header.
- `multimon[filtered]: ... ZCZC...` means the filtered decoder caught the SAME header.
- EOM only means the decoder caught the end marker but missed the header.
- `nwr/alert/same` in the MQTT audit means Home Assistant should have received an alert event.

## SDR Tuning Notes

Do not assume maximum gain is best. Too much gain can overload the receiver.

Recommended tuning process:

1. Start with a known working NWR frequency.
2. Confirm voice audio is clean.
3. Try a gain sweep around 20, 30, 40, and 49.6.
4. Compare raw vs filtered decoder logs during weekly tests.
5. Adjust antenna placement before adding more DSP complexity.
