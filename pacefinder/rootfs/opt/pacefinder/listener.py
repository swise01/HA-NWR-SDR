"""
Pacefinder Listener
Supports: Forza Motorsport, Assetto Corsa Competizione, F1 (Codemasters 2023/2024)
Listens on all three ports simultaneously, auto-detects game from packet size/id.
Saves raw archives and structured JSON sessions to USB storage.
Exposes local web status server at http://pi.local:8000
"""

import asyncio
import collections
import json
import logging
import shutil
import socket
import threading
import urllib.parse
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from net.pages.dashboard import DASHBOARD_HTML
from net.pages.setup import SETUP_HTML
from net.pages.admin import ADMIN_HTML
from net.pages.sessions import (
    SESSIONS_HTML,
    TRACK_DETAIL_HTML_PRE, TRACK_DETAIL_HTML_POST,
    SESSION_DETAIL_HTML_PRE, SESSION_DETAIL_HTML_MID, SESSION_DETAIL_HTML_POST,
)
from net.pages.cars import (
    CAR_DETAIL_HTML_PRE,
    CAR_INDEX_HTML_PRE,
)
from net.pages.circuits import CIRCUIT_INDEX_HTML_PRE
from net.pages.home import HOME_HTML_PRE
from net.pages.events import SESSION_EVENTS_HTML
from net.pages.telemetry import TELEMETRY_HTML
from net.pages.debug import DEBUG_RAW_HTML, DEBUG_PERF_HTML
from net.router import make_handler
from net.api import (
    build_inject_packets as _build_inject_packets_core,
    build_analysis_prompt as _build_analysis_prompt_core,
    build_track_tip_prompt as _build_track_tip_prompt,
    call_claude_api as _call_claude_api_core,
)
from parsers.forza import FM_PACKET_SIZE, FM_PACKET_SIZE_FH, FM_FORMAT, FM_FORMAT_FH, FM_FIELDS
from parsers.acc import parse_acc
from parsers.f1 import F1_HEADER_SIZE, parse_f1
from reference.loader import (
    FORZA_TRACKS, FORZA_CARS, FM2023_TRACKS,
    load_forza_reference_data, parse_forza,
)
from session.manager import (
    _is_driving, Session, state, last_parsed, active_sessions, update_state,
)
from session.protocol import TelemetryProtocol
from session.watchdog import session_watchdog, _clear_race_ended
from config import (
    load_config, save_config, config, storage_path,
    PORTS, SESSION_TIMEOUT_S, IDLE_TIMEOUT_S, STATUS_PORT, LOG_LEVEL,
)
from db.store import (
    initialize as _db_initialize,
    _db_lock,
    _db_connect,
    _db_init,
    _load_learned_track_ordinals,
    _db_write_learned_ordinal,
    _db_get_car_nickname,
    _db_get_car_nicknames,
    _db_set_car_nickname,
    _effective_tracks,
    _classify_race_type,
    _db_cull_ghost_sessions,
    _db_backfill_track_names,
    _db_write_session,
    _db_sessions_list,
    _db_needs_review_count,
    _db_sessions_since_count,
    _db_games_index,
    _db_career_kpis,
    _db_form_data,
    _db_recent_sessions,
    _db_tracks_index,
    _db_track_sessions,
    _db_get_track_tip,
    _db_save_track_tip,
    _db_update_session,
    _db_drop_last_lap,
    _db_delete_session,
    _db_get_ai_analysis,
    _db_save_ai_analysis,
    _db_get_lap_samples,
    _db_get_all_lap_samples,
    _decode_samples,
    _store_session_lap_samples,
    _backfill_lap_samples,
    _update_track_references_bg,
)

_listener_started_at = None  # float, set in main()
_started_at: list = [None]  # mutable ref for router closure
_DEMO_DB_PATH_REF: list = [None]  # mutable ref; set by --demo flag; overrides storage_path()/simtelemetry.db

# ─── Logging ──────────────────────────────────────────────────────────────────

# Bootstrap log dir before logger is configured; use default path if storage
# doesn't exist yet so the process doesn't crash on first run.
_log_dir = Path(config["storage_path"]) / "logs"
try:
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_handler = logging.FileHandler(_log_dir / "listener.log")
except OSError:
    _log_handler = logging.StreamHandler()  # fallback if path isn't mounted yet

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[_log_handler, logging.StreamHandler()],
)
log = logging.getLogger("pacefinder")

# ─── Debug Console ────────────────────────────────────────────────────────────

_debug_clients: list = []
_debug_buffer: collections.deque = collections.deque(maxlen=500)

def _debug_push(line: str):
    _debug_buffer.append(line)
    for q in list(_debug_clients):
        try:
            q.put_nowait(line)
        except Exception:
            pass

class _DebugLogHandler(logging.Handler):
    def emit(self, record):
        _debug_push(self.format(record))

_dbg_log_handler = _DebugLogHandler()
_dbg_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
log.addHandler(_dbg_log_handler)

# ─── Storage Setup ────────────────────────────────────────────────────────────

def ensure_storage():
    for subdir in ["raw", "sessions", "logs"]:
        (storage_path() / subdir).mkdir(parents=True, exist_ok=True)

def disk_info() -> dict:
    """Return free/total bytes for the storage path volume."""
    try:
        usage = shutil.disk_usage(storage_path())
        return {
            "total_gb": round(usage.total / 1e9, 1),
            "used_gb":  round(usage.used  / 1e9, 1),
            "free_gb":  round(usage.free  / 1e9, 1),
        }
    except OSError:
        return {"total_gb": None, "used_gb": None, "free_gb": None}

def _get_local_ips() -> list:
    """Return non-loopback IPv4 addresses on all local interfaces."""
    ips: list = []
    seen: set = set()
    # Primary route — UDP trick sends no actual packets
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            seen.add(ip); ips.append(ip)
    except Exception:
        pass
    # All addresses advertised for this hostname
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip and not ip.startswith("127.") and ip not in seen:
                seen.add(ip); ips.append(ip)
    except Exception:
        pass
    return ips

# ─── Admin Packet Injection ───────────────────────────────────────────────────

def _build_inject_packets(game: str, p: dict) -> list:
    return _build_inject_packets_core(game, p, FM_FORMAT)

# ─── Local Status Server ──────────────────────────────────────────────────────

# Single source of truth for design tokens — injected into every page's <style>
_CSS_TOKENS = """
:root {
  /* Typography */
  --font-mono: 'DM Mono', 'Fira Mono', 'Courier New', monospace;
  --text-xs: clamp(9px, 1.2vw, 11px);
  --text-sm: clamp(11px, 1.5vw, 13px);
  --text-md: clamp(13px, 1.8vw, 15px);
  --text-lg: clamp(16px, 2.5vw, 20px);
  --text-xl: clamp(24px, 4vw, 36px);
  --text-2xl: clamp(36px, 6vw, 56px);
  --fw-normal: 400;
  --fw-medium: 500;
  --fw-bold: 700;
  --fw-black: 900;

  /* Colours */
  --color-bg: #0a0a0a;
  --color-surface: #111111;
  --color-surface-2: #161616;
  --color-border: #1e1e1e;
  --color-border-subtle: #141414;
  --color-text-primary: #ffffff;
  --color-text-secondary: lightgrey;
  --color-text-muted: lightgrey;
  --color-text-dim: lightgrey;
  --color-accent: #e8b84b;
  --color-green: #4ade80;
  --color-red: #f87171;
  --color-blue: #60a5fa;
  --color-amber: #fbbf24;

  /* Spacing */
  --space-1: clamp(4px, 0.5vw, 6px);
  --space-2: clamp(8px, 1vw, 12px);
  --space-3: clamp(12px, 1.5vw, 16px);
  --space-4: clamp(16px, 2vw, 24px);
  --space-6: clamp(24px, 3vw, 36px);
  --space-8: clamp(32px, 4vw, 48px);

  /* Dashboard specific */
  --dash-label-size: clamp(10px, 1.8vw, 14px);
  --dash-value-size: clamp(28px, 6vw, 56px);
  --dash-stat-size: clamp(11px, 1.5vw, 13px);
  --dash-bottom-size: clamp(14px, 2.5vw, 20px);
  --dash-gear-size: clamp(40px, 8vw, 72px);
  --dash-speed-size: clamp(28px, 5vw, 48px);
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;

  /* Legacy aliases — keep old names resolving to new tokens */
  --bg:           var(--color-bg);
  --bg-page:      var(--color-bg);
  --bg-raised:    var(--color-surface);
  --bg-surface:   var(--color-surface);
  --bg-overlay:   #03030a;
  --surface:      var(--color-surface-2);
  --surface-bd:   #2a2a3a;
  --border:       var(--color-border);
  --border-sub:   var(--color-border-subtle);
  --border-faint: #0e0e0e;
  --text:         var(--color-text-primary);
  --text-head:    var(--color-text-primary);
  --text-label:   var(--color-text-secondary);
  --text-muted:   var(--color-text-secondary);
  --text-dim:     var(--color-text-muted);
  --text-ghost:   var(--color-text-dim);
  --accent:       var(--color-accent);
  --accent-soft:  var(--color-green);
  --accent-bg:    #4ade8018;
  --accent-bd:    #4ade8044;
  --accent-bd2:   #4ade8088;
  --danger:       var(--color-red);
  --danger-alpha: #f8717144;
  --danger-glow:  #ef000066;
  --warn:         var(--color-amber);
  --warn-bg:      #1a130a;
  --warn-bd:      #fbbf2444;
  --warn-bg2:     #fbbf2418;
  --info:         var(--color-blue);
  --n-900: #080808;
  --n-800: #111111;
  --n-700: #1a1a1a;
  --n-600: #2a2a2a;
  --n-500: var(--color-text-muted);
  --n-400: var(--color-text-secondary);
  --n-300: var(--color-text-secondary);
  --n-200: var(--color-text-secondary);
  --n-100: #aaaaaa;
  /* Text size scale — legacy aliases */
  --text-2xs: var(--text-xs);
  --text-val: var(--dash-value-size);
  /* Spacing — legacy aliases */
  --sp-1: var(--space-1);
  --sp-2: var(--space-2);
  --sp-3: var(--space-3);
  --sp-4: var(--space-4);
  --sp-5: clamp(20px, 2.5vw, 28px);
  --sp-6: var(--space-6);
}
"""

_PAGE_STYLE = '<link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/base.css">'








TRACK_DETAIL_HTML = TRACK_DETAIL_HTML_PRE + json.dumps(FM2023_TRACKS, ensure_ascii=False) + TRACK_DETAIL_HTML_POST


# CAR_CATALOG is the FORZA_CARS dict reduced to a sorted list of display
# strings ("2018 Honda Civic Type R") for the autocomplete picker on the
# session-edit modal. Sorted alphabetically so the dropdown reads naturally.
_CAR_CATALOG = sorted({c["name"] for c in FORZA_CARS.values() if c.get("name")})
SESSION_DETAIL_HTML = (
    SESSION_DETAIL_HTML_PRE
    + json.dumps(FM2023_TRACKS, ensure_ascii=False)
    + SESSION_DETAIL_HTML_MID
    + json.dumps(_CAR_CATALOG, ensure_ascii=False)
    + SESSION_DETAIL_HTML_POST
)
# Car detail page — currently no embedded constants, so PRE alone is
# the whole page. Kept as a constant for parity with the other pages.
CAR_DETAIL_HTML = CAR_DETAIL_HTML_PRE
CAR_INDEX_HTML = CAR_INDEX_HTML_PRE
CIRCUIT_INDEX_HTML = CIRCUIT_INDEX_HTML_PRE
HOME_HTML = HOME_HTML_PRE


# ─── AI Analysis ──────────────────────────────────────────────────────────────


def _build_analysis_prompt(session: dict, laps: list, historical: list,
                           prev_analyses=None) -> str:
    return _build_analysis_prompt_core(session, laps, historical,
                                       storage_path() / "sessions", prev_analyses)


def _call_claude_api(prompt: str) -> str:
    return _call_claude_api_core(
        prompt,
        config.get("anthropic_api_key", "").strip(),
        config.get("anthropic_model", "claude-sonnet-4-6").strip(),
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main(demo_mode: bool = False):
    global _listener_started_at
    _listener_started_at = time.time()
    _started_at[0] = _listener_started_at
    ensure_storage()
    _db_initialize(_DEMO_DB_PATH_REF, storage_path, FORZA_TRACKS, FORZA_CARS, log)
    _db_init()
    load_forza_reference_data()
    # FORZA_CARS is populated by load_forza_reference_data(); SESSION_DETAIL_HTML
    # was computed at module-import time when the dict was still empty. Rebuild
    # it now so CAR_CATALOG (and TRACK_NAMES) reflect the loaded data.
    global SESSION_DETAIL_HTML, TRACK_DETAIL_HTML
    _car_catalog = sorted({c["name"] for c in FORZA_CARS.values() if c.get("name")})
    SESSION_DETAIL_HTML = (
        SESSION_DETAIL_HTML_PRE
        + json.dumps(FM2023_TRACKS, ensure_ascii=False)
        + SESSION_DETAIL_HTML_MID
        + json.dumps(_car_catalog, ensure_ascii=False)
        + SESSION_DETAIL_HTML_POST
    )
    TRACK_DETAIL_HTML = TRACK_DETAIL_HTML_PRE + json.dumps(FM2023_TRACKS, ensure_ascii=False) + TRACK_DETAIL_HTML_POST
    _db_cull_ghost_sessions()
    _db_backfill_track_names()
    threading.Thread(target=_backfill_lap_samples, daemon=True).start()
    log.info("Pacefinder listener starting%s...", " [DEMO MODE]" if demo_mode else "")

    loop = asyncio.get_event_loop()

    if not demo_mode:
        parsers = {
            "forza_motorsport": parse_forza,
            "acc":              parse_acc,
            "f1":               parse_f1,
        }

        for game, port in PORTS.items():
            try:
                await loop.create_datagram_endpoint(
                    lambda g=game, p=parsers[game]: TelemetryProtocol(g, p, _debug_push),
                    local_addr=("0.0.0.0", port),
                )
                state["bound_ports"][game] = port
                log.info(f"Listening for {game} on UDP port {port}")
            except OSError as e:
                log.error(f"Failed to bind {game} on port {port}: {e} — F1/ACC/Forza port conflict?")

        asyncio.create_task(session_watchdog())

    _ctx = {
        "state": state,
        "last_parsed": last_parsed,
        "config": config,
        "log": log,
        "PORTS": PORTS,
        "active_sessions": active_sessions,
        "debug_clients": _debug_clients,
        "debug_buffer": _debug_buffer,
        "started_at": _started_at,
        "static_dir": Path(__file__).parent / "static",
        "DASHBOARD_HTML": DASHBOARD_HTML,
        "SETUP_HTML": SETUP_HTML,
        "ADMIN_HTML": ADMIN_HTML,
        "SESSIONS_HTML": SESSIONS_HTML,
        "TRACK_DETAIL_HTML": TRACK_DETAIL_HTML,
        "SESSION_DETAIL_HTML": SESSION_DETAIL_HTML,
        "CAR_DETAIL_HTML": CAR_DETAIL_HTML,
        "CAR_INDEX_HTML": CAR_INDEX_HTML,
        "CIRCUIT_INDEX_HTML": CIRCUIT_INDEX_HTML,
        "SESSION_EVENTS_HTML": SESSION_EVENTS_HTML,
        "HOME_HTML": HOME_HTML,
        "TELEMETRY_HTML": TELEMETRY_HTML,
        "DEBUG_RAW_HTML": DEBUG_RAW_HTML,
        "DEBUG_PERF_HTML": DEBUG_PERF_HTML,
        "get_local_ips": _get_local_ips,
        "disk_info": disk_info,
        "save_config": save_config,
        "storage_path": storage_path,
        "effective_tracks": _effective_tracks,
        "FM2023_TRACKS": FM2023_TRACKS,
        "FORZA_CARS": FORZA_CARS,
        "db_sessions_list": _db_sessions_list,
        "db_needs_review_count": _db_needs_review_count,
        "db_sessions_since_count": _db_sessions_since_count,
        "db_games_index": _db_games_index,
        "db_career_kpis": _db_career_kpis,
        "db_form_data": _db_form_data,
        "db_recent_sessions": _db_recent_sessions,
        "db_tracks_index": _db_tracks_index,
        "db_track_sessions": _db_track_sessions,
        "db_get_track_tip": _db_get_track_tip,
        "db_save_track_tip": _db_save_track_tip,
        "build_track_tip_prompt": _build_track_tip_prompt,
        "call_claude_api": _call_claude_api,
        "db_connect": _db_connect,
        "db_lock": _db_lock,
        "db_get_ai_analysis": _db_get_ai_analysis,
        "db_save_ai_analysis": _db_save_ai_analysis,
        "db_update_session": _db_update_session,
        "db_drop_last_lap": _db_drop_last_lap,
        "db_delete_session": _db_delete_session,
        "db_write_learned_ordinal": _db_write_learned_ordinal,
        "db_get_car_nickname": _db_get_car_nickname,
        "db_get_car_nicknames": _db_get_car_nicknames,
        "db_set_car_nickname": _db_set_car_nickname,
        "db_get_lap_samples": _db_get_lap_samples,
        "db_get_all_lap_samples": _db_get_all_lap_samples,
        "decode_samples": _decode_samples,
        "build_inject_packets": _build_inject_packets,
        "build_analysis_prompt": _build_analysis_prompt,
        "clear_race_ended": _clear_race_ended,
    }
    handle_status = make_handler(_ctx)

    server = await asyncio.start_server(handle_status, "0.0.0.0", STATUS_PORT)
    log.info(f"Storage path: {storage_path()}")
    log.info(f"Dashboard at http://localhost:{STATUS_PORT}/")
    log.info(f"Setup     at http://localhost:{STATUS_PORT}/setup")
    log.info(f"Admin     at http://localhost:{STATUS_PORT}/admin")
    log.info(f"Status API at http://localhost:{STATUS_PORT}/status")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    import argparse as _argparse
    _parser = _argparse.ArgumentParser(description="Pacefinder listener")
    _parser.add_argument("--demo", action="store_true",
                         help="Demo mode: skip UDP listeners, serve HTTP only")
    _parser.add_argument("--db", type=str, default=None,
                         help="Path to SQLite database file (used with --demo)")
    _parser.add_argument("--port", type=int, default=None,
                         help="HTTP server port (overrides config/default)")
    _args = _parser.parse_args()

    if _args.demo and _args.db:
        _DEMO_DB_PATH_REF[0] = _args.db
    if _args.port:
        STATUS_PORT = _args.port

    asyncio.run(main(demo_mode=_args.demo))
