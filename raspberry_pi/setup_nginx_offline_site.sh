#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   sudo bash raspberry_pi/setup_nginx_offline_site.sh [FRONTEND_BUILD_DIR]
#
# Example:
#   sudo bash raspberry_pi/setup_nginx_offline_site.sh /opt/visitor-monitor/frontend-stable/build

FRONTEND_BUILD_DIR="${1:-/opt/visitor-monitor/frontend-stable/build}"
NGINX_SITE="/etc/nginx/sites-available/visitor-monitor"
NGINX_LINK="/etc/nginx/sites-enabled/visitor-monitor"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash raspberry_pi/setup_nginx_offline_site.sh ..."
  exit 1
fi

if [[ ! -d "${FRONTEND_BUILD_DIR}" ]]; then
  echo "Frontend build directory not found: ${FRONTEND_BUILD_DIR}"
  echo "Build frontend first: cd frontend-stable && npm ci && npm run build"
  exit 1
fi

apt-get update
apt-get install -y nginx

cat > "${NGINX_SITE}" <<EOF
server {
    listen 80;
    server_name _;

    root ${FRONTEND_BUILD_DIR};
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /socket.io/ {
        proxy_pass http://127.0.0.1:5000/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }
}
EOF

rm -f /etc/nginx/sites-enabled/default
ln -sf "${NGINX_SITE}" "${NGINX_LINK}"
nginx -t
systemctl enable nginx
systemctl restart nginx

echo "Nginx is serving frontend from: ${FRONTEND_BUILD_DIR}"
echo "App URL: http://192.168.4.1 (or http://visitorpi.local)"
