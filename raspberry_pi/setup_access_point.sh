#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   sudo bash raspberry_pi/setup_access_point.sh [SSID] [PASSPHRASE] [COUNTRY_CODE]
#
# Example:
#   sudo bash raspberry_pi/setup_access_point.sh VisitorMonitor Visitor@12345 IN

SSID="${1:-VisitorMonitor}"
PASSPHRASE="${2:-Visitor@12345}"
COUNTRY_CODE="${3:-IN}"
WLAN_IFACE="${WLAN_IFACE:-wlan0}"
AP_IP="${AP_IP:-192.168.4.1}"
DHCP_START="${DHCP_START:-192.168.4.10}"
DHCP_END="${DHCP_END:-192.168.4.200}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash raspberry_pi/setup_access_point.sh ..."
  exit 1
fi

if [[ "${#PASSPHRASE}" -lt 8 || "${#PASSPHRASE}" -gt 63 ]]; then
  echo "PASSPHRASE must be 8..63 characters for WPA2."
  exit 1
fi

echo "[1/6] Installing AP packages..."
apt-get update
apt-get install -y hostapd dnsmasq avahi-daemon qrencode

systemctl stop hostapd || true
systemctl stop dnsmasq || true
systemctl unmask hostapd || true

echo "[2/6] Writing hostapd config..."
cat > /etc/hostapd/hostapd.conf <<EOF
country_code=${COUNTRY_CODE}
interface=${WLAN_IFACE}
driver=nl80211
ssid=${SSID}
hw_mode=g
channel=6
ieee80211n=1
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=${PASSPHRASE}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

if grep -q '^DAEMON_CONF=' /etc/default/hostapd; then
  sed -i 's|^DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
else
  echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' >> /etc/default/hostapd
fi

echo "[3/6] Configuring static AP IP in dhcpcd..."
DHCPCD_FILE="/etc/dhcpcd.conf"
BLOCK_START="# VISITOR_MONITOR_AP_START"
BLOCK_END="# VISITOR_MONITOR_AP_END"
TMP_FILE="$(mktemp)"

awk -v start="${BLOCK_START}" -v end="${BLOCK_END}" '
  $0==start {skip=1; next}
  $0==end {skip=0; next}
  !skip {print}
' "${DHCPCD_FILE}" > "${TMP_FILE}"
cat "${TMP_FILE}" > "${DHCPCD_FILE}"
rm -f "${TMP_FILE}"

cat >> "${DHCPCD_FILE}" <<EOF
${BLOCK_START}
interface ${WLAN_IFACE}
  static ip_address=${AP_IP}/24
  nohook wpa_supplicant
${BLOCK_END}
EOF

echo "[4/6] Configuring dnsmasq DHCP..."
cat > /etc/dnsmasq.d/visitor-monitor-ap.conf <<EOF
interface=${WLAN_IFACE}
bind-dynamic
domain-needed
bogus-priv
dhcp-range=${DHCP_START},${DHCP_END},255.255.255.0,24h
EOF

echo "[5/6] Enabling AP services..."
systemctl restart dhcpcd
systemctl enable hostapd dnsmasq avahi-daemon
systemctl restart hostapd dnsmasq avahi-daemon

echo "[6/6] Done."
echo "Access Point SSID: ${SSID}"
echo "LAN Gateway URL: http://${AP_IP}"
echo "mDNS URL (if supported): http://visitorpi.local"
echo "Reboot once if wlan0 was previously managed by another network setup."
