# Pacefinder

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Latest tag](https://img.shields.io/github/v/tag/Estetika101/pacefinderapp?label=version)](https://github.com/Estetika101/pacefinderapp/tags)

Records UDP telemetry from Forza Motorsport. Saves every session automatically and serves a live dashboard and analysis tools to any device on your network.

Start a race. It records. Stop racing. It stops.

Runs on any always-on machine — Mac, Windows, Linux, Raspberry Pi. Pure Python 3.9+, one external dependency (`anthropic`, only needed for AI coaching).

**[pacefinder.app](https://pacefinder.app)**

---

## What's included

**Always on, no configuration required:**
- **Live dashboard** — speed, throttle, brake, rear slip, tyre temps streamed to any device at 10Hz
- **Session recording** — every session archived automatically to disk and SQLite
- **Session history** — browse by game, circuit, and date with lap trends and career KPIs
- **Lap comparison** — compare any lap against your personal best or theoretical best

**Optional — bring your own Anthropic API key:**
- **Spotter** — post-race AI coaching based on your actual telemetry and historical baseline at each circuit. Add your key in the setup page at `http://localhost:8000/setup`. Costs pennies per session.

---

## Ports

| Game | UDP Port |
|------|----------|
| Forza Motorsport | 5300 |

Listens for both Forza Motorsport (2023) and Forza Horizon 5 — auto-detected by packet size.

> **Roadmap:** ACC and F1 support are coming soon. Parser code is in tree but not bound at startup until the Forza experience is rock-solid.

---

## Quick Start

**Mac / Linux / Pi**
```bash
git clone https://github.com/Estetika101/pacefinderapp
cd pacefinderapp
python3 listener.py
```

**Windows**
```
git clone https://github.com/Estetika101/pacefinderapp
cd pacefinderapp
python listener.py
```
Python 3.9+ required — download from [python.org/downloads](https://python.org/downloads). Check "Add Python to PATH" during install.

Open `http://localhost:8000` and point your game's Data Out to this machine's IP.

Full setup guide at [pacefinder.app](https://pacefinder.app#install)

---

## Auto-start

### Mac
```bash
bash install-mac.sh
```
Installs a launchd service that starts Pacefinder on login and restarts it if it crashes.
Logs: `~/Library/Logs/pacefinder.log`

### Linux / Pi
```bash
sudo cp pacefinder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pacefinder
sudo systemctl start pacefinder
```

> **Already installed under the old `simtelemetry` name?** Migrate with:
> ```bash
> sudo systemctl stop simtelemetry
> sudo systemctl disable simtelemetry
> sudo rm /etc/systemd/system/simtelemetry.service
> sudo cp pacefinder.service /etc/systemd/system/
> sudo systemctl daemon-reload
> sudo systemctl enable pacefinder
> sudo systemctl start pacefinder
> ```

### Windows
Open Task Scheduler → Create Basic Task → Trigger: At log on → Action: Start `pythonw.exe C:\path\to\listener.py`.

---

## Game Setup

### Forza Motorsport
Settings → HUD and Gameplay → Data Out
- Data Out: **ON**
- Data Out IP Address: this machine's IP
- Data Out IP Port: **5300**
- Data Out Packet Format: **Car Dash**

### Forza Horizon 5
Settings → HUD and Gameplay → Data Out
- Data Out: **ON**
- Data Out IP Address: this machine's IP
- Data Out IP Port: **5300**

(Same port as Forza Motorsport — packet format is auto-detected.)

---

## Data Captured

- Speed, throttle %, brake %, clutch %, gear, RPM, steering
- All 4 tyre slip ratios and angles (RL/RR especially useful for traction analysis)
- Tyre temps (FL/FR/RL/RR), and tyre wear in Forza Horizon 5
- Suspension travel, wheel rotation speeds
- Lateral / longitudinal G-forces
- Boost, fuel, best/last/current lap time
- Car ordinal, class, performance index, drivetrain
- Track ordinal (Forza Horizon 5 only — auto-resolved to track name)

---

## File Structure

```
{storage_path}/
  simtelemetry.db           ← SQLite (sessions + AI coaching cache)
  raw/                      ← raw UDP packet archives (.bin)
  sessions/
    <session_id>.json       ← session summary + lap times
    <session_id>_laps.json  ← full per-sample lap data
  logs/
    listener.log
```

Default storage path is `./data/`. Change it in the setup page or edit `simtelemetry.config.json`.

---

## Running as a Background Service (Linux / Pi)

```bash
sudo cp pacefinder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pacefinder
sudo systemctl start pacefinder
```

Check status: `sudo systemctl status pacefinder`

---

## Replay & Analysis

Re-parse a raw `.bin` archive without the listener running:

```bash
# Per-lap summary (auto-detects game)
python3 replay.py path/to/archive.bin --summary

# Export as CSV
python3 replay.py archive.bin --csv > session.csv

# Export as JSON
python3 replay.py archive.bin > session.json
```

---

## Troubleshooting

**No data received:**
- Confirm game Data Out IP matches this machine's IP
- Check firewall: `sudo ufw allow 5300/udp`
- Verify with: `sudo tcpdump -i any udp port 5300`

**Port already in use:**
```bash
sudo lsof -i :5300
```

**Service not starting:**
```bash
sudo journalctl -u pacefinder -f
```

---

## License

MIT — read it, run it, fork it.

## Acknowledgements

The bundled Forza car ordinal database (`data/fm8_cars.csv`) is sourced from
[bluemanos/forza-motorsport-car-track-ordinal](https://github.com/bluemanos/forza-motorsport-car-track-ordinal).
See [`NOTICE.md`](NOTICE.md) for the full attribution list.

---

*Forza Motorsport is a trademark of Microsoft. Pacefinder is not affiliated with Microsoft.*
