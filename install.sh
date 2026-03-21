#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# PULSE Universal Agent Installer
# Supports: Linux (systemd), macOS (launchd)
# Usage:
#   curl -sSL https://raw.githubusercontent.com/YOUR_ORG/pulse/main/install.sh | \
#     PULSE_API_URL=http://your-pulse-server:8000 bash
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PULSE_API_URL="${PULSE_API_URL:-http://localhost:8000}"
NODE_ID="${NODE_ID:-$(hostname)}"
COLLECT_INTERVAL="${COLLECT_INTERVAL:-10}"
SNMP_TARGETS="${SNMP_TARGETS:-}"
SSH_TARGETS="${SSH_TARGETS:-}"
INSTALL_DIR="${INSTALL_DIR:-/opt/pulse-agent}"
SERVICE_USER="${SERVICE_USER:-pulse}"
LOG_FILE="/var/log/pulse-agent.log"

OS="$(uname -s)"
ARCH="$(uname -m)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[PULSE]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

banner() {
cat << 'EOF'
  ██████  ██    ██ ██      ███████ ███████
  ██   ██ ██    ██ ██      ██      ██
  ██████  ██    ██ ██      ███████ █████
  ██      ██    ██ ██           ██ ██
  ██       ██████  ███████ ███████ ███████

  Universal Infrastructure Agent Installer
EOF
}

# ── Pre-flight checks ────────────────────────────────────────────────────────
check_root() {
  if [[ $EUID -ne 0 ]]; then
    die "Run as root: sudo bash install.sh"
  fi
}

check_python() {
  for py in python3 python; do
    if command -v "$py" &>/dev/null; then
      PYTHON="$py"
      PY_VER=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
      log "Found Python $PY_VER at $(command -v $PYTHON)"
      if python3 -c 'import sys; assert sys.version_info >= (3,9)' 2>/dev/null; then
        return 0
      fi
    fi
  done
  log "Python 3.9+ not found — installing..."
  install_python
}

install_python() {
  if command -v apt-get &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv
  elif command -v yum &>/dev/null; then
    yum install -y -q python3 python3-pip
  elif command -v dnf &>/dev/null; then
    dnf install -y -q python3 python3-pip
  elif command -v brew &>/dev/null; then
    brew install python3
  else
    die "Cannot install Python automatically. Install Python 3.9+ and re-run."
  fi
  PYTHON="python3"
}

check_connectivity() {
  log "Testing connectivity to $PULSE_API_URL ..."
  if curl -sf --max-time 5 "$PULSE_API_URL/health" > /dev/null 2>&1; then
    ok "API reachable"
  else
    warn "Cannot reach $PULSE_API_URL — agent will retry automatically"
  fi
}

# ── Install ──────────────────────────────────────────────────────────────────
create_user() {
  if [[ "$OS" == "Darwin" ]]; then return; fi  # macOS: run as current user
  if ! id "$SERVICE_USER" &>/dev/null; then
    log "Creating service user: $SERVICE_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER" 2>/dev/null || true
  fi
}

install_agent() {
  log "Installing to $INSTALL_DIR ..."
  mkdir -p "$INSTALL_DIR"

  # Write collector.py inline (fetched from server or embedded)
  if curl -sf --max-time 10 "$PULSE_API_URL/agent/collector.py" -o "$INSTALL_DIR/collector.py" 2>/dev/null; then
    ok "Downloaded collector.py from API"
  else
    # Fallback: download from GitHub
    COLLECTOR_URL="https://raw.githubusercontent.com/YOUR_ORG/pulse/main/agent/collector.py"
    if curl -sf --max-time 15 "$COLLECTOR_URL" -o "$INSTALL_DIR/collector.py" 2>/dev/null; then
      ok "Downloaded collector.py from GitHub"
    else
      die "Cannot download collector.py — ensure PULSE_API_URL is reachable or internet access is available"
    fi
  fi

  # Write .env
  cat > "$INSTALL_DIR/.env" << ENVEOF
PULSE_API_URL=$PULSE_API_URL
NODE_ID=$NODE_ID
COLLECT_INTERVAL=$COLLECT_INTERVAL
SNMP_TARGETS=$SNMP_TARGETS
SSH_TARGETS=$SSH_TARGETS
ENVEOF

  # Create virtualenv and install deps
  log "Creating Python virtualenv..."
  $PYTHON -m venv "$INSTALL_DIR/venv"
  "$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
  "$INSTALL_DIR/venv/bin/pip" install --quiet psutil httpx python-dotenv pyyaml pysnmp==5.1.0

  ok "Agent installed at $INSTALL_DIR"
}

# ── Service registration ──────────────────────────────────────────────────────
install_systemd() {
  log "Registering systemd service..."
  cat > /etc/systemd/system/pulse-agent.service << SVCEOF
[Unit]
Description=PULSE Infrastructure Agent
Documentation=https://github.com/YOUR_ORG/pulse
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/collector.py
EnvironmentFile=$INSTALL_DIR/.env
Restart=always
RestartSec=10
StandardOutput=append:$LOG_FILE
StandardError=append:$LOG_FILE
# Allow reading host system files
ReadOnlyPaths=/proc /sys /var/log
CapabilityBoundingSet=CAP_NET_ADMIN CAP_SYS_PTRACE
AmbientCapabilities=CAP_NET_ADMIN CAP_SYS_PTRACE
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
SVCEOF

  systemctl daemon-reload
  systemctl enable pulse-agent
  systemctl start  pulse-agent
  sleep 2
  if systemctl is-active --quiet pulse-agent; then
    ok "pulse-agent service is running"
  else
    warn "Service may have failed — check: journalctl -u pulse-agent -n 50"
  fi
}

install_launchd() {
  log "Registering launchd service (macOS)..."
  PLIST_PATH="/Library/LaunchDaemons/com.pulse.agent.plist"
  cat > "$PLIST_PATH" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.pulse.agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>$INSTALL_DIR/venv/bin/python</string>
    <string>$INSTALL_DIR/collector.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PULSE_API_URL</key>  <string>$PULSE_API_URL</string>
    <key>NODE_ID</key>        <string>$NODE_ID</string>
    <key>COLLECT_INTERVAL</key><string>$COLLECT_INTERVAL</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>$INSTALL_DIR</string>
  <key>StandardOutPath</key>
  <string>$LOG_FILE</string>
  <key>StandardErrorPath</key>
  <string>$LOG_FILE</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
PLISTEOF

  launchctl load -w "$PLIST_PATH"
  ok "com.pulse.agent launchd service loaded"
}

# ── Uninstall ────────────────────────────────────────────────────────────────
uninstall() {
  log "Uninstalling PULSE agent..."
  if command -v systemctl &>/dev/null; then
    systemctl stop pulse-agent 2>/dev/null || true
    systemctl disable pulse-agent 2>/dev/null || true
    rm -f /etc/systemd/system/pulse-agent.service
    systemctl daemon-reload
  fi
  if [[ "$OS" == "Darwin" ]]; then
    launchctl unload /Library/LaunchDaemons/com.pulse.agent.plist 2>/dev/null || true
    rm -f /Library/LaunchDaemons/com.pulse.agent.plist
  fi
  rm -rf "$INSTALL_DIR"
  ok "PULSE agent removed"
  exit 0
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
  banner
  [[ "${1:-}" == "uninstall" ]] && uninstall

  check_root
  check_python
  check_connectivity
  create_user
  install_agent

  if [[ "$OS" == "Linux" ]] && command -v systemctl &>/dev/null; then
    install_systemd
  elif [[ "$OS" == "Darwin" ]]; then
    install_launchd
  else
    warn "No init system detected — start manually:"
    echo "  $INSTALL_DIR/venv/bin/python $INSTALL_DIR/collector.py"
  fi

  echo ""
  echo -e "${GREEN}════════════════════════════════════════════${NC}"
  echo -e "${GREEN}  PULSE agent installed successfully!${NC}"
  echo -e "${GREEN}════════════════════════════════════════════${NC}"
  echo ""
  echo "  Node ID:     $NODE_ID"
  echo "  API:         $PULSE_API_URL"
  echo "  Install dir: $INSTALL_DIR"
  echo "  Log:         $LOG_FILE"
  echo ""
  echo "  Commands:"
  if [[ "$OS" == "Linux" ]] && command -v systemctl &>/dev/null; then
    echo "    Status:  systemctl status pulse-agent"
    echo "    Logs:    journalctl -u pulse-agent -f"
    echo "    Stop:    systemctl stop pulse-agent"
    echo "    Remove:  bash install.sh uninstall"
  elif [[ "$OS" == "Darwin" ]]; then
    echo "    Logs:    tail -f $LOG_FILE"
    echo "    Stop:    launchctl unload /Library/LaunchDaemons/com.pulse.agent.plist"
    echo "    Remove:  sudo bash install.sh uninstall"
  fi
  echo ""
}

main "$@"
