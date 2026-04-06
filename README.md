<div align="center">

# 📡 HA-NWR-SDR

### NOAA Weather Radio Integration for Home Assistant

**Real-time SAME/EAS alert decoding · NWS API fallback · Tiered notifications · Any audio output**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2023.6%2B-41BDF5?logo=home-assistant)](https://www.home-assistant.io/)
[![HACS Cards](https://img.shields.io/badge/Requires-Mushroom%20%2B%20card--mod-orange)](https://hacs.xyz/)
[![RTL-SDR](https://img.shields.io/badge/Optional-RTL--SDR-brightgreen)](https://www.rtl-sdr.com/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

> **Works two ways** — use a cheap RTL-SDR dongle for live over-the-air SAME decoding, or run entirely on the NWS API with no hardware at all. Both modes use the same dashboard and package.

</div>

---

## ✨ What it does

- 🎙️ **Decodes SAME/EAS headers** from your local NWR transmitter in real time using an RTL-SDR + Raspberry Pi  
- 🌐 **Polls the NWS Alerts API** every 60 seconds as a backup (or as your only source if you skip the SDR)  
- 🔔 **5-tier alert system** — Tier 1 (Tornado, Nuclear, etc.) is hardwired on; Tiers 2–5 are individually toggleable  
- 📻 **7 WX channels pre-loaded** — pick your station from a dropdown, no frequency lookup needed  
- 🔊 **Works with any HA media player** — just enter your entity ID; supports TTS and direct streaming  
- 📱 **Tiered push notifications** with per-tier sound selection  
- 🔄 **Dual-source intelligence** — SAME decode + NWS API data merged for best available headline/description  
- 🚨 **Safety relay output** — optionally trigger a strobe or siren on Tier 1 alerts  
- 💓 **Heartbeat watchdog** — notifies you if the Pi parser goes offline  
- 🖥️ **Three-tab Lovelace dashboard** — live monitoring, alert drill-down, and settings *(functional starter — see note below)*  

---

## 📋 Choose your path

| | **Path A — SDR + NWS API** | **Path B — NWS API Only** |
|---|---|---|
| Hardware | Raspberry Pi + RTL-SDR | None |
| Alert source | SAME radio decode + NWS API | NWS API only |
| Alert latency | Seconds (radio speed) | ~60 seconds |
| Setup effort | ~30 minutes | ~5 minutes |
| Works during internet outage | ✅ SAME still decodes | ❌ |
| Cost | ~$25 for RTL-SDR | Free |

> **Tip:** Start with Path B to validate your setup, then add the SDR later for full functionality.

---

## 🗺️ Architecture

```
PATH A — SDR + NWS API                    PATH B — NWS API Only
┌─────────────────────────┐               
│      RASPBERRY PI       │               
│                         │               
│  RTL-SDR → rtl_fm       │               ╔═══════════════╗
│         → multimon-ng   │               ║ HOME ASSISTANT ║
│         → nwr_parser.py │──MQTT──┐      ║               ║
└─────────────────────────┘        │      ║  NWS REST API ║
                                   └─────►║  (60s poll)   ║
                                          ║               ║
                                          ║  Automations  ║
                                          ║  Dashboard    ║
                                          ║  Notify / TTS ║
                                          ╚═══════════════╝
```

---

## 🧰 Hardware (Path A only)

- **Raspberry Pi** — any model with USB (3B+ or Zero 2W recommended)  
- **RTL-SDR dongle** — [RTL-SDR Blog V4](https://www.rtl-sdr.com/buy-rtl-sdr-dongles/) ~$30, includes antenna  
- That's it. A basic wire dipole cut to 17" works great at 162 MHz.

---

## 📡 NWR Frequencies — All 7 Channels Pre-Loaded

The integration ships with all 7 standard NWR frequencies as a selectable dropdown. Just pick the one you can receive best.

| Channel | Frequency |
|---------|-----------|
| WX1 | 162.400 MHz |
| WX2 | 162.425 MHz |
| WX3 | 162.450 MHz |
| WX4 | 162.475 MHz |
| WX5 | 162.500 MHz |
| WX6 | 162.525 MHz |
| WX7 | 162.550 MHz |

**Find your nearest station and its channel:** [NOAA NWR Station Finder](https://www.weather.gov/nwr/station_listing)

---

## 🔔 Alert Tier System

| Tier | Level | Examples | Default |
|------|-------|----------|---------|
| **1** | Imminent Threat | Tornado Warning, Nuclear Warning, Flash Flood Warning | **Always on — cannot disable** |
| **2** | Warning | Severe Thunderstorm, Hurricane, Blizzard, High Wind | On |
| **3** | Watch | Tornado Watch, Flash Flood Watch, Winter Storm Watch | On |
| **4** | Advisory / Statement | Special Weather Statement, Dense Fog, Air Quality | Off |
| **5** | Test | Required Weekly Test, Monthly Test, Demo | Off |

**Full SAME event code reference:** [NWS Event Code Definitions](https://www.weather.gov/nwr/eventcodes)

---

## 🚀 Installation

### Prerequisites

- Home Assistant (2023.6+)
- [HACS](https://hacs.xyz/) installed
- HACS Frontend cards: **Mushroom** and **card-mod**
- An MQTT broker (Mosquitto add-on works great) — **required for Path A, optional for Path B**

---

### Step 1 — Find your NWS Zone ID

You need this for the NWS API, regardless of which path you choose.

1. Go to [api.weather.gov/zones/county](https://api.weather.gov/zones/county)  
2. Search (Ctrl+F) for your state and county  
3. Note the zone ID — looks like `ALZ009` or `OHC049`  
4. Repeat for any additional counties you want to monitor  

---

### Step 2 — Install the HA Package

Copy `homeassistant/packages/nwr.yaml` into your HA `packages/` directory.

Add to `configuration.yaml` if you haven't already:
```yaml
homeassistant:
  packages:
    nwr: !include packages/nwr.yaml
```

Edit `nwr.yaml` — find all `# ← EDIT` comments and fill in your values:

| Placeholder | What to enter |
|-------------|---------------|
| `YOUR_ZONE_1` | NWS zone ID for your primary county |
| `YOUR_ZONE_2` | NWS zone ID for a second county (or same as Zone 1) |
| `notify.YOUR_SERVICE` | Your HA notify service name |
| `media_player.YOUR_PLAYER` | Your media player entity for TTS/audio |

Then **restart Home Assistant**.

---

### Step 3 — Add the Dashboard

1. HA → Settings → Dashboards → **Add Dashboard**
2. Give it a name, e.g. "NWR Weather Radio"
3. Open it → 3-dot menu → **Edit → Raw configuration editor**
4. Paste the contents of `dashboard/nwr_alerts.yaml`
5. Update the two `# ← EDIT` lines with your station name and counties
6. Save

---

### Step 4 (Path A only) — Set up the Raspberry Pi

#### 4a — Install dependencies
```bash
sudo apt-get update && sudo apt-get install -y rtl-sdr multimon-ng python3-pip
pip3 install paho-mqtt

# Prevent the default DVB driver from grabbing the RTL-SDR:
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl.conf
sudo usermod -aG plugdev $USER
sudo reboot
```

#### 4b — Test your SDR
```bash
rtl_test -t          # Should show your device
```

#### 4c — Install and configure the parser
```bash
sudo mkdir -p /opt/nwr
sudo chown $USER /opt/nwr
cp pi/nwr_parser.py /opt/nwr/
```

Edit `/opt/nwr/nwr_parser.py` — fill in the `# ← EDIT` section:
- Your MQTT host/credentials  
- Your FIPS county codes (see below)  
- Channel is controlled from the HA dashboard — no need to set frequency here  

**Finding your FIPS codes:**  
Format: `0` + 2-digit state FIPS + 3-digit county FIPS = 6 digits  
Look up yours at [NOAA FIPS reference](https://www.weather.gov/pimar/PubForecastArea)  
Example: Jefferson County, Alabama → `001073`

#### 4d — Install the service
```bash
sudo cp pi/nwr_parser.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nwr_parser
sudo journalctl -u nwr_parser -f   # Watch for "MQTT connected"
```

---

## ✅ Verification

After setup, confirm these in your HA dashboard:

- [ ] **System Status card** — NWS alert count shows a number (not `unavailable`)  
- [ ] **Path A only:** Parser status shows `running`, heartbeat updates every 60s  
- [ ] **Settings tab** — WX channel selector shows 7 options  
- [ ] **Notification toggles** — Tiers 2–4 respond to toggle  
- [ ] **Test:** Wait for Wednesday ~11am local — the weekly test (RWT) should appear if Tier 5 notify is on  

---

## 🔊 Audio Setup

The integration supports any Home Assistant media player. In the Settings tab, enter your player's entity ID in the **TTS Player** and **Stream Player** fields.

- **TTS mode** — HA reads the alert text aloud via any TTS-capable player (Echo, Google, etc.)  
- **Stream mode** — HA plays a live NWR audio stream URL to any player that supports HTTP streams  

For Path A users wanting to self-host the audio stream, see [docs/audio_streaming.md](docs/audio_streaming.md).

---

## 🖥️ About the Dashboard

The included Lovelace dashboard is a **functional starter** — it works, it shows what you need, and it gets the job done. It is not pretty. The YAML is longer than it should be and there are rough edges I never got around to fixing.

I built this to solve a real problem at my house and decided to share it in case it helps anyone else. I am not a frontend developer and the dashboard shows that.

**If you are more skilled than me at Lovelace, card-mod, or HA dashboards — please make it better.** I genuinely look forward to seeing what the community does with this. A pull request that replaces my dashboard with something cleaner would make my day. Screenshots of your setup are even more welcome.

---

## 🤝 Contributing

This is a community project — PRs, issues, and ideas are all welcome.

Honest assessment of where help is most needed:
- **Dashboard redesign** — the current one works but needs a skilled eye
- **Screenshots** — I haven't added any; if you get this running, a screenshot PR would help everyone
- **Testing on different RTL-SDR hardware** — V3, generic dongles, other tuners
- **Sonos / Google Home audio examples**
- **Non-US / Canadian Weatheradio adaptations** (different SAME codes, frequencies)
- **Android notification optimization**

I built this to scratch my own itch. I look forward to people far more skilled than me taking it somewhere I never could. Please open an issue before large PRs. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📜 License

MIT — free to use, modify, and share.

---

## 🙏 Credits

Built on the shoulders of the open-source community:

- [multimon-ng](https://github.com/EliasOenal/multimon-ng) — SAME/EAS decoder  
- [NWS Alerts API](https://www.weather.gov/documentation/services-web-api) — weather data  
- [RTL-SDR](https://www.rtl-sdr.com/) — the hardware ecosystem  
- [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) — Lovelace UI  
- [card-mod](https://github.com/thomasloven/lovelace-card-mod) — CSS theming  
- [NOAA Weather Radio](https://www.weather.gov/nwr/) — the national network this is built around
