#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   sudo bash raspberry_pi/setup_backend_service.sh [APP_ROOT] [RUN_USER]
#
# Example:
#   sudo bash raspberry_pi/setup_backend_service.sh /opt/visitor-monitor pi

APP_ROOT="${1:-/opt/visitor-monitor}"
RUN_USER="${2:-pi}"
BACKEND_DIR="${APP_ROOT}/backend"
PYTHON_BIN="${APP_ROOT}/venv/bin/python3"
SERVICE_FILE="/etc/systemd/system/visitor-backend.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash raspberry_pi/setup_backend_service.sh ..."
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python runtime not found: ${PYTHON_BIN}"
  echo "Create venv first, e.g.:"
  echo "  python3 -m venv ${APP_ROOT}/venv"
  echo "  ${APP_ROOT}/venv/bin/pip install -r ${APP_ROOT}/backend/requirements.txt"
  exit 1
fi

if [[ ! -f "${BACKEND_DIR}/app.py" ]]; then
  echo "Backend app.py not found under: ${BACKEND_DIR}"
  exit 1
fi

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Visitor Monitor Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${BACKEND_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=FACE_OFFLINE_ONLY=1
ExecStart=${PYTHON_BIN} app.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable visitor-backend
systemctl restart visitor-backend

echo "Backend service enabled and started."
echo "Check status: systemctl status visitor-backend --no-pager"
