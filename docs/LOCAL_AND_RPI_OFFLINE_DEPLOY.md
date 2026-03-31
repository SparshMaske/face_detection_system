# Localhost + Raspberry Pi Offline AP Deployment

This guide is for fully offline deployment where Raspberry Pi hosts:
- backend API
- frontend UI
- local database
- its own Wi-Fi Access Point

No internet is required during runtime.

---

## 1) Localhost deployment (quick run)

From project root:

```bash
docker compose up --build -d
```

Open:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5000/api`

Stop:

```bash
docker compose down
```

---

## 2) Prepare offline model files

The backend is configured for offline model loading (`FACE_OFFLINE_ONLY=1` by default).

If you already have InsightFace model cache locally, copy it into project-local model folder:

```bash
bash raspberry_pi/sync_local_face_models.sh buffalo_s
```

Expected destination:

`backend/models/insightface/models/buffalo_s`

---

## 3) (Optional) Build wheelhouse for offline pip install

On an internet-connected machine:

```bash
python3 -m venv .venv-offline
source .venv-offline/bin/activate
pip install --upgrade pip
pip download -r backend/requirements.txt -d offline_bundle/wheels
```

Copy `offline_bundle/wheels` to Raspberry Pi.

Install on Pi:

```bash
/opt/visitor-monitor/venv/bin/pip install --no-index --find-links /opt/visitor-monitor/offline_bundle/wheels -r /opt/visitor-monitor/backend/requirements.txt
```

---

## 4) Raspberry Pi app + service setup

Assume project path on Pi is `/opt/visitor-monitor`.

### 4.1 Backend service auto-start on power-on

```bash
sudo bash raspberry_pi/setup_backend_service.sh /opt/visitor-monitor pi
```

### 4.2 Build frontend once and serve via nginx

```bash
cd /opt/visitor-monitor/frontend-stable
npm ci
npm run build
sudo bash /opt/visitor-monitor/raspberry_pi/setup_nginx_offline_site.sh /opt/visitor-monitor/frontend-stable/build
```

---

## 5) Configure Raspberry Pi as Wi-Fi Access Point

```bash
sudo bash /opt/visitor-monitor/raspberry_pi/setup_access_point.sh VisitorMonitor Visitor@12345 IN
```

This creates AP with:
- SSID: `VisitorMonitor` (example)
- gateway URL: `http://192.168.4.1`
- optional mDNS URL: `http://visitorpi.local`

---

## 6) Generate QR codes (Wi-Fi + App URL)

```bash
cd /opt/visitor-monitor
bash raspberry_pi/generate_qr.sh http://192.168.4.1 VisitorMonitor Visitor@12345 raspberry_pi/qr
```

Generated:
- `raspberry_pi/qr/wifi_qr.png` (join AP)
- `raspberry_pi/qr/app_url_qr.png` (open app)

Phone flow:
1. Scan Wi-Fi QR and connect to Pi AP.
2. Scan App URL QR to open system UI.

---

## 7) Recommended backend `.env` on Pi

```env
DATABASE_URL=postgresql://visitor_user:visitor_pass@localhost:5432/visitor_monitoring
SECRET_KEY=change_this_secret
JWT_SECRET_KEY=change_this_jwt_secret

FACE_MODEL_NAME=buffalo_s
FACE_MODEL_ROOT=/opt/visitor-monitor/backend/models/insightface
FACE_OFFLINE_ONLY=1

CORS_ORIGINS=http://localhost,http://127.0.0.1,http://192.168.4.1,http://visitorpi.local
```

---

## 8) Validate

```bash
curl http://127.0.0.1:5000/api/health
systemctl status visitor-backend --no-pager
systemctl status nginx --no-pager
systemctl status hostapd --no-pager
systemctl status dnsmasq --no-pager
```

If all are active, your system is ready for offline operation through Raspberry Pi AP.
