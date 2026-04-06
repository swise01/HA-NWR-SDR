# Configuration Guide

This document walks you through a complete installation of the NWR integration from zero.

---

## Prerequisites

- Home Assistant (2023.6 or newer recommended)
- HACS installed ([hacs.xyz](https://hacs.xyz))
- A Raspberry Pi (any model with USB)
- An RTL-SDR dongle
- An MQTT broker reachable from both the Pi and HA (Mosquitto add-on works great)

---

## Step 1 — Find your NWR station

Go to [NOAA's station finder](https://www.weather.gov/nwr/station_listing) and find your nearest station. Note:
- **Station call sign** (e.g. WWF57, KIH54)
- **Frequency** (e.g. 162.400 MHz)
- **Counties covered**

---

## Step 2 — Find your FIPS codes

FIPS codes identify your counties in the SAME system.

Format: `0` + 2-digit state code + 3-digit county code = **6 digits**

Example lookup:
```
https://api.weather.gov/zones/county?state=AL
```

You need two things:
1. **FIPS code** for the Pi parser filter (6-digit format above)
2. **Zone ID** for the NWS REST API (e.g. `ALZ001` or `ALC073`)

You can find zone IDs from:
```
https://api.weather.gov/zones/county?state=XX   (replace XX with your 2-letter state)
```

---

## Step 3 — Set up the Raspberry Pi

### 3a — Install system dependencies

```bash
sudo apt-get update
sudo apt-get install -y rtl-sdr multimon-ng python3-pip git

# Add your user to plugdev for RTL-SDR access
sudo usermod -aG plugdev $USER

# Blacklist the default DVB-T kernel module so rtl_sdr can claim the device
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl.conf
sudo update-initramfs -u
```

Reboot after this step.

### 3b — Test your RTL-SDR

```bash
rtl_test -t
# Should show your device. If permission denied, log out and back in.

# Test reception on your NWR frequency (replace 162550000 with yours):
rtl_fm -f 162550000 -M fm -s 22050 -r 22050 - | multimon-ng -t raw -a EAS -
# Let it run during a weekly test (Wed ~11am local time usually) — you should see ZCZC lines
```

### 3c — Install the parser

```bash
sudo mkdir -p /opt/nwr
sudo chown $USER:$USER /opt/nwr

# Clone the repo
git clone https://github.com/YOUR_USERNAME/nwr-ha-integration.git /tmp/nwr-install
cp /tmp/nwr-install/pi/nwr_parser.py /opt/nwr/

# Install Python dependency
pip3 install paho-mqtt
```

### 3d — Configure nwr_parser.py

Edit `/opt/nwr/nwr_parser.py` and update the `CONFIGURE ME` section:

```python
NWR_FREQUENCY_HZ  = 162_550_000    # Your station's frequency in Hz
RTL_PPM_CORRECTION = 0              # Run `rtl_test -p` for 60+ seconds to find yours
FIPS_FILTER        = ["001073", "001009"]  # Your county FIPS codes
MQTT_HOST          = "192.168.1.x"  # Your HA/Mosquitto IP
MQTT_USER          = "mqtt_user"    # If auth is enabled
MQTT_PASSWORD      = "mqtt_pass"
```

### 3e — Install and start the service

```bash
sudo cp /tmp/nwr-install/pi/nwr_parser.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nwr_parser.service
sudo systemctl start nwr_parser.service

# Check it's running
sudo systemctl status nwr_parser.service
journalctl -u nwr_parser -f
```

You should see `MQTT connected` in the logs and `nwr/status` → `running` in your MQTT broker.

---

## Step 4 — Home Assistant Package

### 4a — Enable packages

In `configuration.yaml`:

```yaml
homeassistant:
  packages:
    nwr: !include packages/nwr.yaml
```

### 4b — Copy the package file

```bash
cp homeassistant/packages/nwr.yaml /config/packages/nwr.yaml
```

### 4c — Edit the package

Open `/config/packages/nwr.yaml` and update all `# CONFIGURE_ME` lines:

| Placeholder | Replace with |
|---|---|
| `ZONE_1` | Your first NWS zone ID (e.g. `ALZ009`) |
| `ZONE_2` | Your second NWS zone ID (e.g. `ALZ073`) |
| `YOUR_NOTIFY_SERVICE` | Your HA notify service (e.g. `notify.mobile_app_my_phone`) |
| `YOUR_TTS_PLAYER` | Your TTS media player entity |
| `YOUR_SAFETY_RELAY` | Your relay switch entity (or remove this automation) |
| `YOUR_PI_IP:8000` | Your Pi's IP and stream port (if using audio streaming) |

### 4d — Restart Home Assistant

Check **Settings → System → Logs** for any errors after restart. All `nwr_*` entities should appear.

---

## Step 5 — Dashboard

### 5a — Install HACS cards

Via HACS → Frontend:
1. Search `Mushroom` → Install
2. Search `card-mod` → Install
3. Restart HA / clear browser cache

### 5b — Add the dashboard

1. Go to **Settings → Dashboards → Add Dashboard**
2. Give it a name (e.g. "NWR Weather Radio")
3. Open the new dashboard → 3-dot menu → **Edit → Raw configuration editor**
4. Paste the contents of `dashboard/nwr_alerts_v2.yaml`
5. Replace all `YOUR_STATION_ID`, `YOUR_CITY`, `YOUR_FREQUENCY`, `YOUR_COUNTIES`, `YOUR_COUNTIES` with your values
6. Replace `CONFIGURE_ME` media_player entity IDs with yours
7. Save

---

## Step 6 — Optional: Audio Streaming

If you want live NWR audio streamed to speakers during alerts, you need to run a streaming server on the Pi. A simple approach using `darkice` + `icecast2`:

```bash
sudo apt-get install -y icecast2 darkice
```

Configure darkice to pipe rtl_fm audio to an Icecast mountpoint. Then set `NWR_AUDIO_URL` in the package template sensor to `http://YOUR_PI_IP:8000/nwr.mp3`.

Detailed audio streaming setup: see `docs/audio_streaming.md` (coming soon / PRs welcome).

---

## Verification Checklist

- [ ] `sensor.nwr_parser_status_display` shows `running`
- [ ] `sensor.nwr_heartbeat` updates every 60 seconds
- [ ] `sensor.nws_active_alert_count` shows a number (not unavailable)
- [ ] MQTT topics `nwr/status`, `nwr/heartbeat` visible in MQTT explorer
- [ ] Dashboard loads without "entity not found" errors
- [ ] Weekly test (typically Wednesday ~11am local) triggers alert stack

---

## Troubleshooting

**Parser won't start / RTL device not found**
```bash
lsusb | grep RTL
rtl_test -t
# If "No supported devices found": check USB connection, try different port
```

**MQTT connection refused**
- Verify MQTT broker is running: `sudo systemctl status mosquitto`
- Check firewall: `sudo ufw allow 1883`
- Verify credentials match what's in the package and parser

**NWS REST sensors unavailable**
- Verify zone IDs: `curl "https://api.weather.gov/alerts/active?zone=YOUR_ZONE"`
- Check HA logs for REST sensor errors

**Dashboard cards not rendering**
- Confirm Mushroom and card-mod are installed via HACS
- Clear browser cache after installing HACS cards
- Check browser console for JS errors

**No SAME alerts decoding**
- Run multimon-ng manually and listen during a test broadcast
- Verify frequency and PPM correction
- Check antenna connection — a bad antenna = no decodes
