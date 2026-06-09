#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LISTENER="$SCRIPT_DIR/listener.py"
PLIST_SRC="$SCRIPT_DIR/com.pacefinder.listener.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.pacefinder.listener.plist"
LOG_DIR="$HOME/Library/Logs"
LABEL="com.pacefinder.listener"

if [ ! -f "$LISTENER" ]; then
  echo "Error: listener.py not found at $LISTENER" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

# Unload existing service if running
launchctl list | grep -q "$LABEL" && launchctl unload "$PLIST_DST" 2>/dev/null || true

# Stamp the real paths into the plist
sed \
  -e "s|__LISTENER_PATH__|$LISTENER|g" \
  -e "s|__USER__|$USER|g" \
  -e "s|__WORKING_DIR__|$SCRIPT_DIR|g" \
  "$PLIST_SRC" > "$PLIST_DST"

launchctl load "$PLIST_DST"

echo "Pacefinder installed and started."
echo "Dashboard: http://localhost:8000"
echo "Logs:      tail -f $LOG_DIR/pacefinder.log"
echo "Stop:      launchctl unload $PLIST_DST"
