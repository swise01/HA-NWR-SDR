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
git clone https://github.com/swise01/HA-NWR-SDR.git /tmp/nwr-install
cp /tmp/nwr-install/pi/nwr_parser.py /opt/nwr/

# Install Python dependency
pip3 install paho-mqtt
```

### 3d — Configure nwr_parser.py

Edit `/opt/nwr/nwr_parser.py` and update the `# ← EDIT THIS SECTION` block near the top:

```python
MQTT_HOST       = "homeassistant.local"  # ← EDIT: your MQTT broker IP or hostname
MQTT_PORT       = 1883
MQTT_USER       = ""                     # ← EDIT: leave blank if no auth
MQTT_PASSWORD   = ""                     # ← EDIT: leave blank if no auth

FIPS_FILTER = [
    # "0SSCCC",    # ← EDIT: add your county FIPS codes here
]
```

> **Note:** You do NOT set a frequency here. The active WX channel is controlled from your HA dashboard — when you change the channel selector, HA sends the new frequency to the parser via MQTT and it restarts the SDR pipeline automatically. The default startup channel is WX7 (162.550 MHz) and can be changed from the Settings tab in the dashboard.

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

Open `/config/packages/nwr.yaml` and find all `# ← EDIT` comments. There are about 10 of them:

| Placeholder | Replace with |
|---|---|
| `YOUR_ZONE_1` | Your first NWS zone ID (e.g. `ALZ009`) |
| `YOUR_ZONE_2` | Your second NWS zone ID (e.g. `ALZ073`) |
| `notify.YOUR_SERVICE` | Your HA notify service (e.g. `notify.mobile_app_my_phone`) |
| `media_player.YOUR_PLAYER` | Your TTS media player entity |
| `switch.YOUR_SAFETY_RELAY` | Your relay/switch entity for Tier 1 (or remove that automation) |

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
5. Find the `# ← EDIT` comments at the top of the file and fill in your station name, city, and county names
6. Save

> **Heads up:** The dashboard is a functional starter — it works and shows everything you need, but it's not polished. It was built by someone who knows weather radio, not someone who knows Lovelace. PRs to improve it are very welcome.

---

## Step 6 — Optional: Audio Streaming

The parser includes a built-in audio stream — `rtl_fm` is piped through `ffmpeg` with a volume boost and served as an MP3 stream on port 8765. No extra software needed.

Stream URL: `http://YOUR_PI_IP:8765/nwr.mp3`

In the HA Settings tab, enter this URL in the **Stream Player URL** field and set your media player entity. HA will play the stream to your speaker when an alert fires.

See [docs/audio_streaming.md](docs/audio_streaming.md) for tuning and player examples.

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
