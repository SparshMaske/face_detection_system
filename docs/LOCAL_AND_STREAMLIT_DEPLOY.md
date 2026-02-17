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

Streamlit is used as a shareable host page and embeds your exact React UI.

### Step A: Host your web app frontend publicly
- Deploy frontend URL publicly (for example on Render/Vercel/Netlify), pointing API to your hosted backend.
- Confirm the frontend URL works directly first.

### Step B: Deploy this repo on Streamlit Community Cloud
- App file: `streamlit_app.py`
- Python dependencies file: `requirements.txt`

Set secret/env:
- `STREAMLIT_EMBED_URL=https://your-public-frontend-url`

Then Streamlit link becomes shareable:
- `https://<your-app>.streamlit.app`

Optional override per link:
- `https://<your-app>.streamlit.app/?app=https://your-public-frontend-url`

### Local Streamlit run (optional)

```bash
pip install -r streamlit-requirements.txt
streamlit run streamlit_app.py
```

Open:
- `http://localhost:8501` (defaults to `http://localhost:3000`)
- Optional override: `http://localhost:8501/?app=http://localhost:3000`

## Notes
- This preserves the same UI/UX because Streamlit embeds the same React app.
- Browser camera/RTSP behavior depends on your hosted frontend/backend deployment and HTTPS permissions.
