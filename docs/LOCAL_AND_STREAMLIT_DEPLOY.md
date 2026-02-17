# Localhost + Streamlit Deployment

## 1) Localhost deployment (full app, same UI/UX)

From project root:

```bash
docker compose up --build -d
```

Alternative (if you want to run compose file from `docker/` folder directly):

```bash
docker compose -f docker/docker-compose.yml up --build -d
```

Open:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5000/api`

Stop:

```bash
docker compose down
```

## 2) Streamlit deployment (shareable link, same UI/UX)

Streamlit serves your React build from this repo on the same Streamlit URL.

### Step A: Host backend publicly
- Deploy backend API publicly (Render/Railway/VM/etc.) so mobile users can access it over HTTPS.
- Confirm `https://<backend-domain>/api/health` (or any API endpoint) works.

### Step B: Deploy this repo on Streamlit Community Cloud
- App file: `streamlit_app.py`
- Python dependencies file: `requirements.txt`
- System packages file: `packages.txt` (installs Node/NPM for first-time frontend build)

Backend URL configuration (optional but recommended):
- Streamlit defaults to `/api` so the app opens directly without pre-errors.
- If your backend is on another domain, set one of:
  - Streamlit Secrets: `BACKEND_API_URL="https://your-backend-domain"`
  - Env var: `BACKEND_API_URL=https://your-backend-domain`
  - Query override: `?api=https://your-backend-domain`

Then Streamlit link becomes shareable:
- `https://<your-app>.streamlit.app`

Optional backend override per link:
- `https://<your-app>.streamlit.app/?api=https://your-backend-domain`

### Local Streamlit run (optional)

```bash
pip install -r streamlit-requirements.txt
cd frontend-stable && npm run build && cd ..
streamlit run streamlit_app.py
```

Open:
- `http://localhost:8501`
- Optional backend override: `http://localhost:8501/?api=http://127.0.0.1:5000`

## Notes
- This preserves the same UI/UX by loading the same built React app inside Streamlit.
- For phone users, backend must be HTTPS and CORS must allow your Streamlit domain.
