#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

[[ ${EUID:-$(id -u)} -eq 0 ]] || {
  printf 'host install audit must run as root\n' >&2
  exit 1
}

./install.sh install --no-start

[[ $(stat -c '%U:%G:%a' /opt/nwr/nwr_parser.py) == root:nwr:750 ]]
[[ $(stat -c '%U:%G:%a' /opt/nwr/config.env) == root:nwr:640 ]]
[[ $(stat -c '%U:%G:%a' /var/lib/nwr) == nwr:nwr:750 ]]
[[ $(stat -c '%U:%G:%a' /etc/systemd/system/nwr.service) == root:root:644 ]]
[[ $(stat -c '%U:%G:%a' /usr/local/sbin/nwrctl) == root:root:755 ]]
[[ -x /opt/nwr_venv/bin/python3 ]]
[[ $(nwrctl version) == 'nwrctl 4.1.0' ]]
if systemctl is-active --quiet nwr.service; then
  printf 'fresh install started nwr.service unexpectedly\n' >&2
  exit 1
fi
multimon-ng -a EAS -t raw /dev/null 2>&1 | grep -q EAS
/opt/nwr_venv/bin/python3 -c 'import paho.mqtt.client, dotenv'

sed -i 's/^MQTT_HOST=.*/MQTT_HOST=127.0.0.1/' /opt/nwr/config.env
sed -i 's/^MQTT_PASS=.*/MQTT_PASS=ci-audit-value/' /opt/nwr/config.env
config_before=$(sha256sum /opt/nwr/config.env)

python3 -m http.server 1883 --bind 127.0.0.1 >/tmp/nwr-ci-audit-http.log 2>&1 &
audit_server_pid=$!
trap 'kill "$audit_server_pid" 2>/dev/null || true' EXIT
for _ in {1..20}; do
  nc -z 127.0.0.1 1883 2>/dev/null && break
  sleep 0.1
done
nwrctl check

./install.sh update --skip-packages --no-start
config_after=$(sha256sum /opt/nwr/config.env)
[[ "$config_before" == "$config_after" ]]

./install.sh uninstall

[[ -f /opt/nwr/config.env ]]
[[ -d /var/lib/nwr ]]
id nwr >/dev/null
[[ ! -e /opt/nwr/nwr_parser.py ]]
[[ ! -e /opt/nwr_venv ]]
[[ ! -e /etc/systemd/system/nwr.service ]]
[[ ! -e /usr/local/sbin/nwrctl ]]

printf 'cloud host install audit passed\n'
