#!/bin/bash
set -eu

CONFIG="${MQTT_AUDIT_CONFIG:-/opt/nwr/config.env}"
LOG_DIR="${MQTT_AUDIT_LOG_DIR:-/home/pi/logs/mqtt}"
AUDIT_LOG_FILE="${MQTT_AUDIT_LOG_FILE:-$LOG_DIR/pi-mqtt.log}"
AUDIT_TOPICS="${MQTT_AUDIT_TOPICS:-nwr/#}"

if [ -r "$CONFIG" ]; then
    # shellcheck disable=SC1090
    . "$CONFIG"
fi

: "${MQTT_HOST:=localhost}"
: "${MQTT_PORT:=1883}"
: "${MQTT_USER:=}"
: "${MQTT_PASS:=}"

mkdir -p "$LOG_DIR"

args=(-h "$MQTT_HOST" -p "$MQTT_PORT" -R -v)
for topic in $AUDIT_TOPICS; do
    args+=(-t "$topic")
done
if [ -n "$MQTT_USER" ]; then
    args+=(-u "$MQTT_USER")
fi
if [ -n "$MQTT_PASS" ]; then
    args+=(-P "$MQTT_PASS")
fi

# Intentionally keep credentials out of logs. Payloads are written verbatim.
# -R skips retained startup state so this is an event log, not a state dump.
mosquitto_sub "${args[@]}" | while IFS= read -r line; do
    printf '%s %s\n' "$(date -Is)" "$line"
done >> "$AUDIT_LOG_FILE"
