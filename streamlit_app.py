import json
import os
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="Visitor Monitor",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      #MainMenu, header, footer {visibility: hidden;}
      .block-container {padding: 0 !important; max-width: 100% !important;}
      [data-testid="stAppViewContainer"] {background: #0b1220;}
      [data-testid="stToolbar"] {right: 0.5rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


ROOT_DIR = Path(__file__).resolve().parent
BUILD_DIR = ROOT_DIR / "frontend-stable" / "build"


def _query_param(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return str(value).strip()


def _secret_value(*names: str) -> str:
    for name in names:
        try:
            value = st.secrets.get(name, "")
        except Exception:
            value = ""
        if isinstance(value, list):
            value = str(value[0]).strip() if value else ""
        else:
            value = str(value).strip()
        if value:
            return value
    return ""


def _env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_api_url(url: str) -> str:
    clean = url.strip().rstrip("/")
    if not clean:
        return "/api"
    if clean.startswith("/"):
        return clean if clean.endswith("/api") else f"{clean}/api"
    if _is_http_url(clean):
        return clean if clean.endswith("/api") else f"{clean}/api"
    return "/api"


@st.cache_data(show_spinner=False)
def _load_frontend_assets() -> tuple[str, str]:
    manifest_path = BUILD_DIR / "asset-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            "Missing frontend build at frontend-stable/build. "
            "Run `npm run build` in frontend-stable and commit build artifacts."
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    css_rel = manifest.get("files", {}).get("main.css", "")
    js_rel = manifest.get("files", {}).get("main.js", "")
    if not css_rel or not js_rel:
        raise RuntimeError("Build manifest missing main.css or main.js")

    css_path = BUILD_DIR / css_rel.lstrip("/")
    js_path = BUILD_DIR / js_rel.lstrip("/")
    if not css_path.exists() or not js_path.exists():
        raise FileNotFoundError("Frontend bundle files are missing. Rebuild and commit frontend-stable/build.")

    css_bundle = css_path.read_text(encoding="utf-8", errors="ignore")
    js_bundle = js_path.read_text(encoding="utf-8", errors="ignore")
    return css_bundle, js_bundle


def _render_frontend(api_base_url: str) -> None:
    css_bundle, js_bundle = _load_frontend_assets()

    # Runtime patch API endpoint to avoid rebuilding for env changes.
    js_bundle = js_bundle.replace("http://127.0.0.1:5000/api", api_base_url)
    js_bundle = js_bundle.replace("http://localhost:5000/api", api_base_url)

    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Visitor Monitoring System</title>
    <style>{css_bundle}</style>
  </head>
  <body>
    <div id="root"></div>
    <div id="streamlit-runtime-error" style="display:none;white-space:pre-wrap;background:#2a1114;color:#fecaca;padding:12px;margin:8px;border-radius:8px;font-family:monospace;font-size:12px;"></div>
    <script>
      if (!window.location.hash) {{
        window.location.hash = '#/login';
      }}
      function showErr(msg) {{
        var box = document.getElementById('streamlit-runtime-error');
        if (!box) return;
        box.style.display = 'block';
        box.textContent = msg;
      }}
      window.addEventListener('error', function (event) {{
        showErr('Frontend runtime error: ' + (event.message || 'Unknown error'));
      }});
      window.addEventListener('unhandledrejection', function (event) {{
        showErr('Frontend unhandled rejection: ' + String(event.reason || 'Unknown reason'));
      }});
    </script>
    <script>{js_bundle}</script>
  </body>
</html>
"""
    components.html(html, height=1000, scrolling=True)


api_from_query = _query_param("api")
api_from_secret = _secret_value(
    "BACKEND_API_URL",
    "STREAMLIT_BACKEND_API_URL",
    "API_BASE_URL",
    "STREAMLIT_API_URL",
)
api_from_env = _env_value(
    "BACKEND_API_URL",
    "STREAMLIT_BACKEND_API_URL",
    "API_BASE_URL",
    "STREAMLIT_API_URL",
)
default_api = _env_value("DEFAULT_BACKEND_API_URL", "DEFAULT_API_URL") or "/api"
api_url = api_from_query or api_from_secret or api_from_env or default_api
api_base_url = _normalize_api_url(api_url)

try:
    _render_frontend(api_base_url)
except Exception as exc:
    st.error("Failed to render frontend in Streamlit.")
    st.code(str(exc))
