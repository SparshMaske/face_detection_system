#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash raspberry_pi/generate_qr.sh [APP_URL] [SSID] [PASSPHRASE] [OUT_DIR]
#
# Example:
#   bash raspberry_pi/generate_qr.sh http://192.168.4.1 VisitorMonitor Visitor@12345 raspberry_pi/qr

APP_URL="${1:-http://192.168.4.1}"
SSID="${2:-VisitorMonitor}"
PASSPHRASE="${3:-Visitor@12345}"
OUT_DIR="${4:-raspberry_pi/qr}"

mkdir -p "${OUT_DIR}"

if ! command -v qrencode >/dev/null 2>&1; then
  echo "qrencode not found."
  echo "Install with: sudo apt-get install -y qrencode"
  exit 1
fi

WIFI_PAYLOAD="WIFI:T:WPA;S:${SSID};P:${PASSPHRASE};;"

qrencode -o "${OUT_DIR}/app_url_qr.png" "${APP_URL}"
qrencode -o "${OUT_DIR}/wifi_qr.png" "${WIFI_PAYLOAD}"

echo "Generated:"
echo "  ${OUT_DIR}/app_url_qr.png"
echo "  ${OUT_DIR}/wifi_qr.png"
echo
echo "Phone flow:"
echo "1) Scan wifi_qr.png and join AP."
echo "2) Scan app_url_qr.png to open app."
