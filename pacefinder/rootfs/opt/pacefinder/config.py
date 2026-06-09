import json
import logging
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "simtelemetry.config.json"

DEFAULTS: dict = {
    "storage_path":      "/mnt/usb/simtelemetry",
    "session_timeout_s": 10,
    "idle_timeout_s":    30,
    "status_port":       8000,
    "ports": {
        # ACC (9996) and F1 (20777) are PARKED — see docs/specs/park-acc-f1.md
        "forza_motorsport": 5300,
    },
    "anthropic_api_key": "",
    "anthropic_model":   "claude-sonnet-4-6",
    # UI-only display preference. "24h" (default) or "12h".
    # See docs/specs/time-format-preference.md.
    "time_format":       "24h",
    # When true, the live dashboard speaks an audible "I think the race
    # is over" the moment race-end is detected — a diagnostic aid for
    # validating race-end timing against what actually happened on track.
    "debug_mode":        False,
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
            merged = {**DEFAULTS, **saved}
            # Only honor saved port overrides for known/active games.
            # Stale acc/f1 keys in user configs are ignored (parked).
            saved_ports = {k: v for k, v in saved.get("ports", {}).items() if k in DEFAULTS["ports"]}
            merged["ports"] = {**DEFAULTS["ports"], **saved_ports}
            return merged
        except Exception:
            pass
    return {**DEFAULTS, "ports": {**DEFAULTS["ports"]}}


def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


config = load_config()

_LOCAL_FALLBACK = Path(__file__).parent / "data"


def storage_path() -> Path:
    """Return the active storage root, falling back to a local data/ dir if USB isn't mounted."""
    p = Path(config["storage_path"])
    if p.exists():
        return p
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError:
        _LOCAL_FALLBACK.mkdir(parents=True, exist_ok=True)
        return _LOCAL_FALLBACK


PORTS             = config["ports"]
SESSION_TIMEOUT_S = config["session_timeout_s"]
IDLE_TIMEOUT_S    = config["idle_timeout_s"]
STATUS_PORT       = config["status_port"]
LOG_LEVEL         = logging.INFO

# Floor below which a lap_time_s is treated as an out-lap or partial. Used by
# the session-close filter and the theoretical-best calculation. 20s is shorter
# than any real circuit lap, so anything under it is structurally suspect.
MIN_VALID_LAP_S = 20.0
