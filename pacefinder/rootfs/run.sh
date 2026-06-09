#!/usr/bin/with-contenv sh
set -eu

python3 - <<'PY'
import json
from pathlib import Path

options_path = Path("/data/options.json")
options = {
    "web_port": 8000,
    "udp_port": 8000,
    "storage_path": "/data/pacefinder",
}
if options_path.exists():
    options.update(json.loads(options_path.read_text()))

storage = Path(str(options["storage_path"]))
storage.mkdir(parents=True, exist_ok=True)
for child in ("raw", "sessions", "logs"):
    (storage / child).mkdir(parents=True, exist_ok=True)

config = {
    "storage_path": str(storage),
    "session_timeout_s": 10,
    "idle_timeout_s": 30,
    "status_port": int(options["web_port"]),
    "ports": {
        "forza_motorsport": int(options["udp_port"]),
    },
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-4-6",
    "time_format": "24h",
    "debug_mode": False,
}
Path("/opt/pacefinder/simtelemetry.config.json").write_text(json.dumps(config, indent=2))
PY

exec python3 /opt/pacefinder/listener.py
