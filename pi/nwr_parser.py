#!/usr/bin/env python3
"""
nwr_parser.py
=============
Decode SAME/EAS headers and publish normalized JSON to MQTT.
Alert routing and user actions belong in Home Assistant.

Topics published:
  nwr/alert/same    JSON on ZCZC header received
  nwr/alert/eom     JSON on NNNN (end of message) received
  nwr/audio/url     HTTP stream URL (on startup, retained)
  nwr/status        running / LWT offline (retained)

SAME JSON payload includes:
  issue_utc           — reconstructed from JJJHHMM field (NWS issue time)
  issue_expiry_utc    — issue_utc + valid_duration (identical on every rebroadcast)
  true_remaining_secs — seconds left from now based on issue_expiry_utc
  received_utc        — when Pi actually received the broadcast
"""

import json
import logging
import os
import queue
import re
import socket
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paho.mqtt.client as mqtt
from dotenv import dotenv_values

CFG_PATH = os.environ.get("NWR_CONFIG", "/opt/nwr/config.env")
cfg = dotenv_values(CFG_PATH)

MQTT_HOST       = cfg.get("MQTT_HOST", "localhost")
MQTT_PORT       = int(cfg.get("MQTT_PORT", 1883))
MQTT_USER       = cfg.get("MQTT_USER", "")
MQTT_PASS       = cfg.get("MQTT_PASS", "")
TOPIC_ROOT      = cfg.get("MQTT_TOPIC_ROOT", "nwr")
SDR_FREQ        = cfg.get("SDR_FREQUENCY", "162.550M")
SDR_DEV        = cfg.get("SDR_DEVICE_INDEX", "0")
SDR_RATE       = cfg.get("SDR_SAMPLE_RATE", "32000")
SAME_RATE      = cfg.get("SAME_SAMPLE_RATE", "22050")
SDR_GAIN       = cfg.get("SDR_GAIN", "28.0")
SDR_PPM        = cfg.get("SDR_PPM", "0")
SDR_DEEMP      = cfg.get("SDR_DEEMPHASIS", "true").lower() in ("1", "true", "yes", "on")
SDR_DC_BLOCK   = cfg.get("SDR_DC_BLOCK", "true").lower() in ("1", "true", "yes", "on")
SDR_FIR        = cfg.get("SDR_FIR", "true").lower() in ("1", "true", "yes", "on")
FIPS_FILTER_RAW = cfg.get("FIPS_FILTER", "")
AUDIO_PORT      = int(cfg.get("AUDIO_STREAM_PORT", 8765))
AUDIO_STREAM_URL = cfg.get("AUDIO_STREAM_URL", "").strip()
AUDIO_ADVERTISE_HOST = cfg.get("AUDIO_ADVERTISE_HOST", "").strip()
LOG_LEVEL       = cfg.get("LOG_LEVEL", "INFO")
LOG_FILE        = cfg.get("LOG_FILE", "")
MQTT_CLIENT_ID  = cfg.get(
    "MQTT_CLIENT_ID", f"nwr_same_parser-{socket.gethostname()}"
).strip()
MQTT_TLS        = cfg.get("MQTT_TLS", "false").lower() in ("1", "true", "yes", "on")
MQTT_CA_CERT    = cfg.get("MQTT_CA_CERT", "").strip()
PIPELINE_POLL_SECONDS = 2.0

TOPIC_ROOT = str(TOPIC_ROOT).strip().strip("/")
if not TOPIC_ROOT or "+" in TOPIC_ROOT or "#" in TOPIC_ROOT or "//" in TOPIC_ROOT:
    raise ValueError("MQTT_TOPIC_ROOT must be non-empty and contain no wildcards")

FIPS_FILTER = set(f.strip() for f in FIPS_FILTER_RAW.split(",") if f.strip())

log_handlers = [logging.StreamHandler()]
if LOG_FILE:
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        log_handlers.append(logging.FileHandler(LOG_FILE))
    except Exception as exc:
        log_handlers[0].handle(logging.makeLogRecord({
            "levelno": logging.WARNING,
            "levelname": "WARNING",
            "msg": f"Could not open parser log file {LOG_FILE}: {exc}",
        }))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=log_handlers,
)
log = logging.getLogger("nwr")

SAME_RE = re.compile(
    r"ZCZC-"
    r"(?P<org>[A-Z]{3})-"
    r"(?P<event>[A-Z0-9]{3})-"
    r"(?P<counties>[\d-]+)\+"
    r"(?P<valid_hours>\d{2})"
    r"(?P<valid_mins>\d{2})-"
    r"(?P<issue_day>\d{3})"
    r"(?P<issue_hhmm>\d{4})-"
    r"(?P<wfo>.+)"
)

AUDIO_CHUNK     = 4096
_stream_clients = set()
_stream_lock    = threading.Lock()
_same_seen      = {}
_last_eom_seen  = 0.0
_alert_clear_timer = None
_alert_clear_token = None
_alert_clear_lock = threading.Lock()

def _register_client(q):
    with _stream_lock:
        _stream_clients.add(q)

def _unregister_client(q):
    with _stream_lock:
        _stream_clients.discard(q)

def _broadcast_audio(chunk):
    with _stream_lock:
        dead = set()
        for q in _stream_clients:
            try:
                q.put_nowait(chunk)
            except queue.Full:
                dead.add(q)
        _stream_clients.difference_update(dead)

class _AudioHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/nwr.mp3", "/"):
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = queue.Queue(maxsize=64)
        _register_client(q)
        log.info("Audio client connected from %s", self.client_address[0])
        try:
            while True:
                chunk = q.get(timeout=15)
                self.wfile.write(chunk)
                self.wfile.flush()
        except Exception:
            pass
        finally:
            _unregister_client(q)
            log.info("Audio client disconnected from %s", self.client_address[0])

    def log_message(self, fmt, *args):
        log.debug("HTTP " + fmt, *args)

def _start_audio_http_server():
    server = ThreadingHTTPServer(("0.0.0.0", AUDIO_PORT), _AudioHandler)
    server.daemon_threads = True
    t = threading.Thread(target=server.serve_forever, daemon=True, name="audio-http")
    t.start()
    log.info("Audio stream server on http://0.0.0.0:%d/nwr.mp3", AUDIO_PORT)

def _ffmpeg_broadcast(ffmpeg_proc):
    try:
        while True:
            chunk = ffmpeg_proc.stdout.read(AUDIO_CHUNK)
            if not chunk:
                break
            _broadcast_audio(chunk)
    except Exception as exc:
        log.error("ffmpeg broadcast error: %s", exc)

def _report_pipeline_exit(line_queue, source, detail):
    try:
        line_queue.put_nowait(("__pipeline_exit__", f"{source}: {detail}"))
    except queue.Full:
        pass


def _log_process_stderr(proc, source, line_queue):
    try:
        for raw_bytes in proc.stderr:
            line = raw_bytes.decode("utf-8", errors="ignore").strip()
            if line:
                lowered = line.lower()
                level = log.error if any(
                    marker in lowered
                    for marker in ("pll not locked", "failed", "error", "overflow", "lost")
                ) else log.info
                level("%s: %s", source, line)
    except Exception as exc:
        log.error("stderr reader failed for %s: %s", source, exc)
    finally:
        _report_pipeline_exit(line_queue, source, f"stderr closed rc={proc.poll()}")


def _tee_audio(rtl_proc, same_stdin_list, ffmpeg_stdin, line_queue):
    try:
        while True:
            chunk = rtl_proc.stdout.read(AUDIO_CHUNK)
            if not chunk:
                break
            for same_stdin in same_stdin_list:
                try:
                    same_stdin.write(chunk)
                    same_stdin.flush()
                except BrokenPipeError:
                    pass
            try:
                ffmpeg_stdin.write(chunk)
                ffmpeg_stdin.flush()
            except BrokenPipeError:
                pass
    except Exception as exc:
        log.error("Audio tee error: %s", exc)
    finally:
        _report_pipeline_exit(line_queue, "rtl_fm", f"audio ended rc={rtl_proc.poll()}")

def _pipe_stream(src, dst, source, line_queue):
    try:
        while True:
            chunk = src.read(AUDIO_CHUNK)
            if not chunk:
                break
            dst.write(chunk)
            dst.flush()
    except Exception as exc:
        log.error("Audio pipe error on %s: %s", source, exc)
    finally:
        _report_pipeline_exit(line_queue, source, "audio pipe ended")

def _read_multimon_lines(mm_proc, source, line_queue):
    try:
        for raw_bytes in mm_proc.stdout:
            line = raw_bytes.decode("utf-8", errors="ignore").strip()
            if line:
                line_queue.put((source, line))
    except Exception as exc:
        log.error("multimon reader error on %s decoder: %s", source, exc)
    finally:
        _report_pipeline_exit(
            line_queue, f"multimon-{source}", f"output ended rc={mm_proc.poll()}"
        )

def _normalize_multimon_line(line):
    return line.replace("EAS: ", "").replace("SAME: ", "").strip()

def _recent_same(raw):
    now = time.monotonic()
    cutoff = now - 15
    for seen_raw, seen_at in list(_same_seen.items()):
        if seen_at < cutoff:
            del _same_seen[seen_raw]
    if raw in _same_seen:
        _same_seen[raw] = now
        return True
    _same_seen[raw] = now
    return False

try:
    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                     client_id=MQTT_CLIENT_ID, clean_session=True)
except AttributeError:
    mq = mqtt.Client(client_id=MQTT_CLIENT_ID, clean_session=True)

if MQTT_USER:
    mq.username_pw_set(MQTT_USER, MQTT_PASS)
if MQTT_TLS:
    mq.tls_set(ca_certs=MQTT_CA_CERT or None)
mq.will_set(f"{TOPIC_ROOT}/status", payload="offline", retain=True)

def on_connect(client, userdata, flags, rc, properties=None):
    code = rc if isinstance(rc, int) else rc.value
    if code == 0:
        log.info("MQTT connected to %s:%s", MQTT_HOST, MQTT_PORT)
        client.publish(f"{TOPIC_ROOT}/status", "running", qos=1, retain=True)
        client.publish(f"{TOPIC_ROOT}/alert/eom", payload=None, qos=1, retain=True)
        client.subscribe(f"{TOPIC_ROOT}/alert/same", qos=1)
    else:
        log.error("MQTT connect failed rc=%s", rc)

mq.on_connect = on_connect


def on_message(client, userdata, message):
    if message.topic != f"{TOPIC_ROOT}/alert/same" or not message.payload:
        return
    try:
        payload = json.loads(message.payload)
        expiry = datetime.fromisoformat(
            str(payload["issue_expiry_utc"]).replace("Z", "+00:00")
        )
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        remaining = int(
            (expiry.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        )
        token = str(payload.get("raw") or payload["issue_expiry_utc"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        log.warning("Could not restore retained SAME expiry: %s", exc)
        return
    if remaining <= 0:
        pub("alert/same", "", retain=True, qos=1)
        log.info("Cleared stale retained SAME alert on MQTT reconnect")
        return
    _schedule_retained_alert_clear(token, remaining)
    log.info("Restored retained SAME expiry timer with %ds remaining", remaining)


mq.on_message = on_message

def pub(topic, payload, retain=False, qos=0):
    full = f"{TOPIC_ROOT}/{topic}"
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)
    result = mq.publish(full, payload=str(payload), qos=qos, retain=retain)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        log.error("MQTT publish failed for %s rc=%s", full, result.rc)
    log.debug("MQTT -> %s : %s", full, str(payload)[:120])


def _clear_retained_alert(token):
    global _alert_clear_timer, _alert_clear_token
    with _alert_clear_lock:
        if token != _alert_clear_token:
            return
        pub("alert/same", "", retain=True, qos=1)
        _alert_clear_timer = None
        _alert_clear_token = None
    log.info("Cleared expired retained SAME alert")


def _schedule_retained_alert_clear(token, delay_seconds):
    global _alert_clear_timer, _alert_clear_token
    with _alert_clear_lock:
        if _alert_clear_timer:
            _alert_clear_timer.cancel()
        _alert_clear_token = token
        _alert_clear_timer = threading.Timer(
            max(1, delay_seconds), _clear_retained_alert, args=(token,)
        )
        _alert_clear_timer.daemon = True
        _alert_clear_timer.start()

def handle_zczc(raw):
    """
    Parse SAME header and publish raw JSON.
    Computes issue_utc from the JJJHHMM field so expiry is anchored
    to the NWS-issued timestamp, not receive time. Every rebroadcast
    of the same alert produces the same issue_expiry_utc value,
    making extension detection reliable in HA.
    """
    if _recent_same(raw):
        log.info("Duplicate SAME header suppressed")
        return

    m = SAME_RE.search(raw)
    if not m:
        log.warning("Could not parse SAME header: %s", raw)
        return

    g = m.groupdict()
    county_list = [c for c in g["counties"].split("-") if c]

    if FIPS_FILTER:
        matched = [c for c in county_list if c in FIPS_FILTER]
        if not matched:
            log.info("Alert %s ignored — counties %s not in filter %s",
                     g["event"], county_list, FIPS_FILTER)
            return

    valid_hours = int(g["valid_hours"])
    valid_mins  = int(g["valid_mins"])
    valid_secs  = valid_hours * 3600 + valid_mins * 60
    now_utc     = datetime.now(timezone.utc)

    # Reconstruct issue_utc from JJJHHMM
    issue_utc = now_utc
    try:
        julian_day = int(g["issue_day"])
        issue_hour = int(g["issue_hhmm"][:2])
        issue_min  = int(g["issue_hhmm"][2:])
        year       = now_utc.year

        issue_candidate = datetime(year, 1, 1, issue_hour, issue_min,
                                   tzinfo=timezone.utc) + timedelta(days=julian_day - 1)

        # If candidate is more than 12h in the future, it crossed a year boundary
        if (issue_candidate - now_utc).total_seconds() > 43200:
            issue_candidate = datetime(year - 1, 1, 1, issue_hour, issue_min,
                                       tzinfo=timezone.utc) + timedelta(days=julian_day - 1)

        issue_utc = issue_candidate
        log.debug("SAME issue time: %s (Julian %s %02d:%02d UTC)",
                  issue_utc.isoformat(), julian_day, issue_hour, issue_min)

    except Exception as exc:
        log.warning("Could not parse SAME issue time from '%s%s': %s — using receive time",
                    g["issue_day"], g["issue_hhmm"], exc)

    issue_expiry_utc    = issue_utc + timedelta(seconds=valid_secs)
    true_remaining_secs = max(0, int((issue_expiry_utc - now_utc).total_seconds()))

    payload = {
        "event_code":          g["event"],
        "org":                 g["org"],
        "counties":            county_list,
        "wfo":                 g["wfo"].strip(),
        "valid_hours":         valid_hours,
        "valid_mins":          valid_mins,
        "valid_seconds":       valid_secs,
        "issue_utc":           issue_utc.isoformat(),
        "issue_expiry_utc":    issue_expiry_utc.isoformat(),
        "true_remaining_secs": true_remaining_secs,
        "received_utc":        now_utc.isoformat(),
        "raw":                 raw.strip(),
    }

    log.info("SAME -> %s | %s | issued %s | expires %s | %ds remaining",
             g["event"], county_list,
             issue_utc.strftime("%H:%M UTC"),
             issue_expiry_utc.strftime("%H:%M UTC"),
             true_remaining_secs)

    if true_remaining_secs <= 0:
        log.warning("Ignoring already-expired SAME alert %s", g["event"])
        return

    pub("alert/same", payload, retain=True, qos=1)
    _schedule_retained_alert_clear(raw.strip(), true_remaining_secs)

def handle_eom():
    global _last_eom_seen
    now_mono = time.monotonic()
    if now_mono - _last_eom_seen < 2:
        log.info("Duplicate EOM suppressed")
        return
    _last_eom_seen = now_mono

    now_utc = datetime.now(timezone.utc)
    log.info("EOM received")
    pub("alert/eom", {"eom_utc": now_utc.isoformat()}, retain=False, qos=1)

def start_sdr_pipeline():
    rtl_cmd = [
        "rtl_fm", "-d", SDR_DEV, "-f", SDR_FREQ, "-M", "fm",
        "-s", SDR_RATE, "-g", SDR_GAIN, "-p", SDR_PPM,
    ]
    if SDR_FIR:
        rtl_cmd.extend(["-F", "9"])
    if SDR_DEEMP:
        rtl_cmd.extend(["-E", "deemp"])
    if SDR_DC_BLOCK:
        rtl_cmd.extend(["-E", "dc"])
    rtl_cmd.append("-")

    same_resampler_cmd = [
        "ffmpeg", "-loglevel", "warning",
        "-f", "s16le", "-ar", SDR_RATE, "-ac", "1", "-i", "pipe:0",
        "-f", "s16le", "-ar", SAME_RATE, "-ac", "1", "pipe:1",
    ]
    same_filter_cmd = [
        "ffmpeg", "-loglevel", "warning",
        "-f", "s16le", "-ar", SDR_RATE, "-ac", "1", "-i", "pipe:0",
        "-af", "highpass=f=300,lowpass=f=2800,volume=6dB,alimiter=limit=0.95",
        "-f", "s16le", "-ar", SAME_RATE, "-ac", "1", "pipe:1",
    ]
    mm_cmd = ["multimon-ng", "-a", "EAS", "-t", "raw", "/dev/stdin"]
    ffmpeg_cmd = [
        "ffmpeg", "-loglevel", "warning",
        "-f", "s16le", "-ar", SDR_RATE, "-ac", "1", "-i", "pipe:0",
        "-af", "highpass=f=350,lowpass=f=2400,adeclick=t=2.0:b=4,afftdn=nf=-25,volume=6dB,alimiter=limit=0.92", "-f", "mp3", "-ab", "64k", "-ar", "22050", "pipe:1",
    ]
    log.info("Starting rtl_fm -> [raw+filtered SAME decoders + MP3 stream] on %s device=%s gain=%s ppm=%s rate=%s",
             SDR_FREQ, SDR_DEV, SDR_GAIN, SDR_PPM, SDR_RATE)
    line_queue              = queue.Queue(maxsize=128)
    rtl_proc                = subprocess.Popen(rtl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    same_resample_proc      = subprocess.Popen(same_resampler_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    same_filter_proc        = subprocess.Popen(same_filter_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    mm_raw_proc             = subprocess.Popen(mm_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    mm_filtered_proc        = subprocess.Popen(mm_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    ffmpeg_proc             = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    same_stdin_list = [same_resample_proc.stdin, same_filter_proc.stdin]
    threading.Thread(target=_tee_audio, args=(rtl_proc, same_stdin_list, ffmpeg_proc.stdin, line_queue), daemon=True, name="audio-tee").start()
    threading.Thread(target=_pipe_stream, args=(same_resample_proc.stdout, mm_raw_proc.stdin, "same-raw-resampler", line_queue), daemon=True, name="same-raw-pipe").start()
    threading.Thread(target=_pipe_stream, args=(same_filter_proc.stdout, mm_filtered_proc.stdin, "same-filtered-resampler", line_queue), daemon=True, name="same-filtered-pipe").start()
    threading.Thread(target=_read_multimon_lines, args=(mm_raw_proc, "raw", line_queue), daemon=True, name="same-raw-reader").start()
    threading.Thread(target=_read_multimon_lines, args=(mm_filtered_proc, "filtered", line_queue), daemon=True, name="same-filtered-reader").start()
    threading.Thread(target=_ffmpeg_broadcast, args=(ffmpeg_proc,), daemon=True, name="audio-broadcast").start()
    for proc, source in (
        (rtl_proc, "rtl_fm"),
        (same_resample_proc, "ffmpeg-same-raw"),
        (same_filter_proc, "ffmpeg-same-filtered"),
        (ffmpeg_proc, "ffmpeg-stream"),
    ):
        threading.Thread(
            target=_log_process_stderr,
            args=(proc, source, line_queue),
            daemon=True,
            name=f"{source}-stderr",
        ).start()
    processes = (
        rtl_proc,
        same_resample_proc,
        same_filter_proc,
        mm_raw_proc,
        mm_filtered_proc,
        ffmpeg_proc,
    )
    return line_queue, processes

def main():
    log.info("NWR parser starting — freq=%s FIPS filter=%s", SDR_FREQ, FIPS_FILTER or "none")
    mq.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mq.loop_start()
    advertise_host = AUDIO_ADVERTISE_HOST
    if not advertise_host:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((MQTT_HOST, MQTT_PORT))
                advertise_host = sock.getsockname()[0]
        except Exception:
            advertise_host = socket.getfqdn()
    stream_url = AUDIO_STREAM_URL or f"http://{advertise_host}:{AUDIO_PORT}/nwr.mp3"
    pub("audio/url", stream_url, retain=True)
    log.info("Audio stream URL: %s", stream_url)
    _start_audio_http_server()
    while True:
        line_queue, processes = start_sdr_pipeline()
        pub("status", "running", retain=True, qos=1)
        try:
            while True:
                try:
                    source, line = line_queue.get(timeout=PIPELINE_POLL_SECONDS)
                except queue.Empty:
                    failed = [
                        (proc.args[0], proc.returncode)
                        for proc in processes
                        if proc.poll() is not None
                    ]
                    if failed:
                        raise RuntimeError(f"child process exited: {failed}")
                    continue
                if source == "__pipeline_exit__":
                    raise RuntimeError(line)
                log.info("multimon[%s]: %s", source, line)
                if "ZCZC" in line:
                    handle_zczc(_normalize_multimon_line(line))
                elif "NNNN" in line:
                    handle_eom()
        except Exception as exc:
            log.error("Pipeline error: %s — restarting in 5s", exc)
            pub("status", "error", retain=True, qos=1)
        finally:
            for proc in reversed(processes):
                try:
                    if proc.poll() is None:
                        proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
        log.info("Restarting pipeline in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    main()
