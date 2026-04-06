#!/usr/bin/env python3
"""
nwr_parser.py — NOAA Weather Radio SAME Decoder + MQTT Publisher
Repository: https://github.com/YOUR_GITHUB_USERNAME/HA-NWR-SDR
Version: 2.0.0

Listens on an RTL-SDR dongle, decodes SAME/EAS headers via multimon-ng,
and publishes structured JSON to MQTT for Home Assistant.

The active WX channel (frequency) is controlled from your HA dashboard —
when you change the channel selector in HA, this script receives the new
frequency over MQTT and automatically restarts the SDR pipeline.

License: MIT
"""

import subprocess
import threading
import time
import json
import re
import logging
import signal
import sys
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

# ─────────────────────────────────────────────────────────────────
#  ← EDIT THIS SECTION for your installation
# ─────────────────────────────────────────────────────────────────

MQTT_HOST       = "homeassistant.local"  # ← EDIT: your MQTT broker IP or hostname
MQTT_PORT       = 1883
MQTT_USER       = ""                     # ← EDIT: leave blank if no auth
MQTT_PASSWORD   = ""                     # ← EDIT: leave blank if no auth
MQTT_TLS        = False                  # ← EDIT: True if your broker uses TLS

# FIPS county filter — only alert codes for these counties will be processed.
# Leave as empty list [] to pass ALL counties (useful for rural areas with few alerts).
# Format: "0SSCCC" — 0 + 2-digit state FIPS + 3-digit county FIPS
# Find yours: https://www.weather.gov/pimar/PubForecastArea
# Example: Jefferson Co. Alabama = "001073", Blount Co. Alabama = "001009"
FIPS_FILTER = [
    # "0SSCCC",    # ← EDIT: add your county codes here
    # "0SSCCC",    # ← EDIT: add more counties if needed
]

# RTL-SDR hardware
RTL_DEVICE_INDEX    = 0      # 0 = first connected dongle
RTL_PPM_CORRECTION  = 0      # Frequency error correction; run `rtl_test -p` to find yours
RTL_GAIN            = "40"   # SDR gain in dB; "0" = automatic

# ─────────────────────────────────────────────────────────────────
#  CONSTANTS — do not edit below this line
# ─────────────────────────────────────────────────────────────────

MQTT_TOPIC_PREFIX   = "nwr"

# All 7 standard NWR frequencies
WX_CHANNELS = {
    "WX1 — 162.400 MHz": 162_400_000,
    "WX2 — 162.425 MHz": 162_425_000,
    "WX3 — 162.450 MHz": 162_450_000,
    "WX4 — 162.475 MHz": 162_475_000,
    "WX5 — 162.500 MHz": 162_500_000,
    "WX6 — 162.525 MHz": 162_525_000,
    "WX7 — 162.550 MHz": 162_550_000,
}
DEFAULT_CHANNEL     = "WX7 — 162.550 MHz"
SAMPLE_RATE         = 22050
HEARTBEAT_INTERVAL  = 60

# Alert tier mapping (used to filter by severity — full table at weather.gov/nwr/eventcodes)
ALERT_TIERS = {
    1: {"TOR","EWW","FFW","TSW","NUW","RHW","HMW","SPW","EVI","CDW","VOW","EQW","LEW","LAW","CEM","EAN"},
    2: {"SVR","BZW","ISW","HUW","WSW","FRW","AVW","SMW","HWW","FLW","DSW","EHW","ECW","TYW"},
    3: {"TOA","SVA","FFA","FLA","HUA","WSA","BZA","AVA","HWA","TYA","TSA","EHA","ECA","FRA","DBA"},
    4: {"SPS","FLS","FFS","HLS","MWS","WIY","WCY","FZW","HZW","FZA","HZA","FWW","DUY","FOG",
        "SBY","BHY","LWY","AQY","ASY","FWA"},
    5: {"RWT","RMT","DMO","NMN","ADR","EAT","NIC","NPT"},
}

ORIGINATOR_CODES = {
    "PEP": "Presidential", "CIV": "Civil Authorities",
    "WXR": "NWS", "EAS": "EAS Participant",
}

SAME_PATTERN = re.compile(
    r"ZCZC-(?P<org>[A-Z]{3})-(?P<event>[A-Z0-9]{3})-"
    r"(?P<locations>(?:\d{6}[+-])+)(?P<duration>\d{4})-"
    r"(?P<issue_time>\d{7})-(?P<callsign>[\w/\-]+)-?"
)

LOG_LEVEL = logging.INFO

# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────

def get_tier(code: str) -> int:
    for tier, codes in ALERT_TIERS.items():
        if code in codes:
            return tier
    return 4

def parse_duration(tttt: str) -> int:
    try:
        return int(tttt[:2]) * 3600 + int(tttt[2:]) * 60
    except Exception:
        return 3600

def parse_issue_time(jjjhhmm: str) -> datetime:
    try:
        doy  = int(jjjhhmm[:3])
        hour = int(jjjhhmm[3:5])
        mins = int(jjjhhmm[5:7])
        base = datetime(datetime.now(timezone.utc).year, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1)
        return base.replace(hour=hour, minute=mins, second=0, microsecond=0)
    except Exception:
        return datetime.now(timezone.utc)

def parse_same_header(line: str) -> dict | None:
    if "ZCZC" not in line:
        return None
    m = SAME_PATTERN.search(line)
    if not m:
        logging.warning("Unparseable SAME header: %s", line.strip())
        return None

    event_code = m.group("event")
    fips_codes  = re.findall(r"\d{6}", m.group("locations"))
    duration_s  = parse_duration(m.group("duration"))
    issue_dt    = parse_issue_time(m.group("issue_time"))
    expiry_dt   = issue_dt + timedelta(seconds=duration_s)

    if FIPS_FILTER:
        matched = [f for f in fips_codes if f in FIPS_FILTER]
        if not matched:
            logging.debug("Alert %s not for our counties — skipping.", event_code)
            return None
        relevant_fips = matched
    else:
        relevant_fips = fips_codes

    return {
        "event_code":  event_code,
        "tier":        get_tier(event_code),
        "originator":  ORIGINATOR_CODES.get(m.group("org"), m.group("org")),
        "fips_codes":  relevant_fips,
        "duration_s":  duration_s,
        "issue_time":  issue_dt.isoformat(),
        "expiry_time": expiry_dt.isoformat(),
        "callsign":    m.group("callsign").strip("-").strip(),
    }

# ─────────────────────────────────────────────────────────────────
#  Main class
# ─────────────────────────────────────────────────────────────────

class NWRParser:
    def __init__(self):
        self._running       = True
        self._restart_sdr   = threading.Event()
        self._active_freq   = WX_CHANNELS.get(DEFAULT_CHANNEL, 162_550_000)
        self._rtl_proc      = None
        self._mm_proc       = None

        self.mqtt = mqtt.Client(client_id="nwr_parser", clean_session=True)
        if MQTT_USER:
            self.mqtt.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        if MQTT_TLS:
            self.mqtt.tls_set()
        self.mqtt.on_connect    = self._on_mqtt_connect
        self.mqtt.on_disconnect = self._on_mqtt_disconnect
        self.mqtt.on_message    = self._on_mqtt_message
        self._mqtt_connected    = False

    # ── MQTT callbacks ──────────────────────────────────────────

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._mqtt_connected = True
            logging.info("MQTT connected to %s:%d", MQTT_HOST, MQTT_PORT)
            # Subscribe to channel change commands from HA
            client.subscribe(f"{MQTT_TOPIC_PREFIX}/set_channel")
            self._pub("status", "running", retain=True)
        else:
            logging.error("MQTT connect failed rc=%d", rc)

    def _on_mqtt_disconnect(self, client, userdata, rc):
        self._mqtt_connected = False
        logging.warning("MQTT disconnected rc=%d", rc)

    def _on_mqtt_message(self, client, userdata, msg):
        """Handle channel change from HA input_select."""
        payload = msg.payload.decode("utf-8", errors="ignore").strip()
        if msg.topic == f"{MQTT_TOPIC_PREFIX}/set_channel":
            freq = WX_CHANNELS.get(payload)
            if freq and freq != self._active_freq:
                logging.info("Channel change → %s (%d Hz)", payload, freq)
                self._active_freq = freq
                self._pub("channel", payload, retain=True)
                self._restart_sdr.set()   # Signal pipeline restart

    # ── MQTT publish helpers ────────────────────────────────────

    def _pub(self, subtopic: str, payload: str, retain: bool = False):
        if not self._mqtt_connected:
            return
        self.mqtt.publish(f"{MQTT_TOPIC_PREFIX}/{subtopic}", payload, qos=1, retain=retain)

    def _heartbeat_loop(self):
        while self._running:
            self._pub("heartbeat", str(int(time.time())), retain=True)
            time.sleep(HEARTBEAT_INTERVAL)

    # ── SDR pipeline ────────────────────────────────────────────

    def _build_pipeline(self):
        rtl_cmd = [
            "rtl_fm",
            "-f", str(self._active_freq),
            "-M", "fm",
            "-s", str(SAMPLE_RATE),
            "-r", str(SAMPLE_RATE),
            "-d", str(RTL_DEVICE_INDEX),
            "-p", str(RTL_PPM_CORRECTION),
            "-g", str(RTL_GAIN),
            "-",
        ]
        mm_cmd = ["multimon-ng", "-t", "raw", "-a", "EAS", "-"]
        return rtl_cmd, mm_cmd

    def _cleanup(self):
        for proc in (self._mm_proc, self._rtl_proc):
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    pass
        self._mm_proc = None
        self._rtl_proc = None

    # ── Main run loop ───────────────────────────────────────────

    def start(self):
        self.mqtt.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.mqtt.loop_start()
        time.sleep(2)

        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        while self._running:
            self._restart_sdr.clear()
            freq_mhz = self._active_freq / 1_000_000
            logging.info("Starting SDR pipeline on %.3f MHz...", freq_mhz)
            self._pub("status", "running", retain=True)

            try:
                rtl_cmd, mm_cmd = self._build_pipeline()
                self._rtl_proc = subprocess.Popen(rtl_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                self._mm_proc  = subprocess.Popen(mm_cmd, stdin=self._rtl_proc.stdout,
                                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                self._rtl_proc.stdout.close()

                for line in self._mm_proc.stdout:
                    if self._restart_sdr.is_set():
                        break
                    line = line.strip()
                    if not line:
                        continue
                    logging.debug("multimon: %s", line)

                    if "NNNN" in line:
                        logging.info("EOM received")
                        self._pub("eom", datetime.now(timezone.utc).isoformat(), retain=True)
                        continue

                    if "ZCZC" in line:
                        alert = parse_same_header(line)
                        if alert:
                            logging.info("ALERT %s tier=%d exp=%s",
                                         alert["event_code"], alert["tier"], alert["expiry_time"])
                            self._pub("alert", json.dumps(alert), retain=True)

            except Exception as exc:
                logging.error("Pipeline error: %s", exc)
                self._pub("status", "error", retain=True)
            finally:
                self._cleanup()
                if self._running and not self._restart_sdr.is_set():
                    logging.info("Pipeline exited unexpectedly — restarting in 10s...")
                    time.sleep(10)

    def stop(self, *_):
        logging.info("Shutting down...")
        self._running = False
        self._pub("status", "stopped", retain=True)
        self._cleanup()
        sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
    parser = NWRParser()
    signal.signal(signal.SIGTERM, parser.stop)
    signal.signal(signal.SIGINT,  parser.stop)
    logging.info("NWR Parser v2.0.0 | FIPS filter: %s", FIPS_FILTER or "ALL COUNTIES")
    parser.start()
