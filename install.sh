#!/usr/bin/env bash
set -Eeuo pipefail

INSTALLER_VERSION="4.1.0"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/nwr"
STATE_DIR="/var/lib/nwr"
VENV_DIR="/opt/nwr_venv"
CONFIG_FILE="/opt/nwr/config.env"
SERVICE_FILE="/etc/systemd/system/nwr.service"
CLI_FILE="/usr/local/sbin/nwrctl"
PACKAGE_LIST=(rtl-sdr multimon-ng ffmpeg netcat-openbsd python3-venv python3-pip mosquitto-clients)
COMMAND="install"
SOURCE_CONFIG=""
SKIP_PACKAGES=false
NO_START=false
DRY_RUN=false

usage() {
  cat <<'EOF'
HA-NWR-SDR host installer

Usage:
  sudo ./install.sh [install|update|uninstall] [options]
  ./install.sh version

Options:
  --config PATH     Install a completed config.env and enable the service
  --skip-packages   Do not run apt-get
  --no-start        Install files without enabling or restarting the service
  --dry-run         Print the installation plan without changing the host
  -h, --help        Show this help

Fresh installs preserve the example config and remain stopped until configured.
Use `sudo nwrctl edit`, then `sudo nwrctl enable`.
EOF
}

log() {
  printf '[nwr-install] %s\n' "$*"
}

die() {
  printf '[nwr-install] ERROR: %s\n' "$*" >&2
  exit 1
}

run() {
  if "$DRY_RUN"; then
    printf '+ '
    printf '%q ' "$@"
    printf '\n'
  else
    "$@"
  fi
}

require_supported_host() {
  [[ -r /etc/os-release ]] || die "Cannot identify this Linux distribution"
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}" in
    debian|ubuntu|raspbian) ;;
    *) die "Supported hosts are Debian, Ubuntu, and Raspberry Pi OS" ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64|aarch64|arm64|armv7l|armv6l) ;;
    *) die "Unsupported architecture: $(uname -m)" ;;
  esac
  command -v systemctl >/dev/null || die "systemd is required"
  if ! "$SKIP_PACKAGES"; then
    command -v apt-get >/dev/null || die "apt-get is required unless --skip-packages is used"
  fi
}

require_sources() {
  local source
  for source in \
    "$ROOT_DIR/pi/nwr_parser.py" \
    "$ROOT_DIR/pi/nwr_parser.service" \
    "$ROOT_DIR/pi/requirements.txt" \
    "$ROOT_DIR/pi/config.env.example" \
    "$ROOT_DIR/pi/nwrctl"; do
    [[ -f "$source" ]] || die "Missing release file: $source"
  done
}

require_root() {
  if ! "$DRY_RUN" && [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    die "Run this command as root (for example: sudo ./install.sh $COMMAND)"
  fi
}

install_packages() {
  "$SKIP_PACKAGES" && return
  log "Installing native radio and audio dependencies"
  run apt-get update
  run env DEBIAN_FRONTEND=noninteractive apt-get install -y "${PACKAGE_LIST[@]}"
}

install_account() {
  log "Creating the unprivileged nwr service account"
  if "$DRY_RUN" || ! id nwr >/dev/null 2>&1; then
    run useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin nwr
  fi
  if getent group plugdev >/dev/null 2>&1 || "$DRY_RUN"; then
    run usermod -aG plugdev nwr
  fi
  run install -d -o nwr -g nwr -m 0750 "$INSTALL_DIR"
  run install -d -o nwr -g nwr -m 0750 "$STATE_DIR"
}

install_driver_policy() {
  local policy=/etc/modprobe.d/blacklist-rtl-sdr.conf
  if ! grep -RqsE '^[[:space:]]*blacklist[[:space:]]+dvb_usb_rtl28xxu([[:space:]]|$)' /etc/modprobe.d 2>/dev/null; then
    log "Preventing the DVB driver from claiming RTL-SDR receivers"
    if "$DRY_RUN"; then
      log "Would write blacklist dvb_usb_rtl28xxu to $policy"
    else
      printf '%s\n' 'blacklist dvb_usb_rtl28xxu' > "$policy"
      chmod 0644 "$policy"
    fi
  fi
}

install_python() {
  log "Building the isolated Python environment"
  if [[ ! -x "$VENV_DIR/bin/python3" ]] || "$DRY_RUN"; then
    run python3 -m venv "$VENV_DIR"
  fi
  run "$VENV_DIR/bin/python3" -m pip install --disable-pip-version-check --upgrade pip
  run "$VENV_DIR/bin/python3" -m pip install --disable-pip-version-check -r "$ROOT_DIR/pi/requirements.txt"
}

install_runtime() {
  log "Installing NWR runtime, service, and management CLI"
  run install -o root -g nwr -m 0750 "$ROOT_DIR/pi/nwr_parser.py" "$INSTALL_DIR/nwr_parser.py"
  run install -o root -g nwr -m 0640 "$ROOT_DIR/pi/requirements.txt" "$INSTALL_DIR/requirements.txt"
  run install -o root -g root -m 0644 "$ROOT_DIR/pi/nwr_parser.service" "$SERVICE_FILE"
  run install -o root -g root -m 0755 "$ROOT_DIR/pi/nwrctl" "$CLI_FILE"
}

install_config() {
  local fresh=false
  if [[ -n "$SOURCE_CONFIG" ]]; then
    [[ -r "$SOURCE_CONFIG" ]] || die "Cannot read config: $SOURCE_CONFIG"
    run install -o root -g nwr -m 0640 "$SOURCE_CONFIG" "$CONFIG_FILE"
  elif [[ ! -e "$CONFIG_FILE" ]]; then
    fresh=true
    run install -o root -g nwr -m 0640 "$ROOT_DIR/pi/config.env.example" "$CONFIG_FILE"
  else
    log "Preserving existing $CONFIG_FILE"
  fi
  "$fresh"
}

config_ready() {
  [[ -r "$CONFIG_FILE" ]] || return 1
  grep -qE '^MQTT_HOST=.+$' "$CONFIG_FILE" || return 1
  ! grep -qE '^MQTT_PASS=change-me$' "$CONFIG_FILE"
}

activate_service() {
  local fresh_config=$1
  run systemctl daemon-reload
  if "$NO_START"; then
    log "Service activation skipped by --no-start"
    return
  fi
  if { "$fresh_config" && [[ -z "$SOURCE_CONFIG" ]]; } || ! config_ready; then
    log "Installation complete; service remains stopped until config.env is configured"
    log "Next: sudo nwrctl edit && sudo nwrctl enable"
    return
  fi
  if systemctl is-enabled --quiet nwr.service 2>/dev/null; then
    run systemctl restart nwr.service
  else
    run systemctl enable --now nwr.service
  fi
}

install_all() {
  local fresh_config=false
  require_supported_host
  require_sources
  require_root
  install_packages
  install_account
  install_driver_policy
  install_python
  install_runtime
  if install_config; then
    fresh_config=true
  fi
  activate_service "$fresh_config"
  log "HA-NWR-SDR host runtime $INSTALLER_VERSION installed"
  log "Run: sudo nwrctl check"
}

uninstall_all() {
  require_supported_host
  require_root
  log "Removing the NWR service and installed program files"
  if systemctl list-unit-files nwr.service --no-legend 2>/dev/null | grep -q '^nwr.service'; then
    run systemctl disable --now nwr.service
  fi
  run rm -f "$SERVICE_FILE" "$CLI_FILE" "$INSTALL_DIR/nwr_parser.py" "$INSTALL_DIR/requirements.txt"
  run rm -rf "$VENV_DIR"
  run systemctl daemon-reload
  log "Preserved $CONFIG_FILE, $STATE_DIR, and the nwr account; native packages were not removed"
}

parse_args() {
  if [[ $# -gt 0 && $1 != -* ]]; then
    COMMAND=$1
    shift
  fi
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --config)
        [[ $# -ge 2 ]] || die "--config requires a path"
        SOURCE_CONFIG=$2
        shift 2
        ;;
      --skip-packages) SKIP_PACKAGES=true; shift ;;
      --no-start) NO_START=true; shift ;;
      --dry-run) DRY_RUN=true; NO_START=true; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "Unknown option: $1" ;;
    esac
  done
  case "$COMMAND" in
    install|update|uninstall|version) ;;
    *) die "Unknown command: $COMMAND" ;;
  esac
}

parse_args "$@"
case "$COMMAND" in
  install|update) install_all ;;
  uninstall) uninstall_all ;;
  version) printf 'nwr-install %s\n' "$INSTALLER_VERSION" ;;
esac
