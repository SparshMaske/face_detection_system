import json
import os
import shutil
import subprocess
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
      [data-testid="stAppViewContainer"] {
        background: #0b1220;
      }
      [data-testid="stToolbar"] {
        right: 0.5rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


ROOT_DIR = Path(__file__).resolve().parent
BUILD_DIR = ROOT_DIR / "frontend-stable" / "build"
FRONTEND_DIR = ROOT_DIR / "frontend-stable"


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


def _read_build_asset(relative_path: str) -> str:
    file_path = BUILD_DIR / relative_path.lstrip("/")
    return file_path.read_text(encoding="utf-8", errors="ignore")


def _ensure_local_build() -> None:
    manifest_path = BUILD_DIR / "asset-manifest.json"
    if manifest_path.exists():
        return

    npm_bin = shutil.which("npm")
    if not npm_bin:
        raise FileNotFoundError(
            "Frontend build missing and npm is not available. "
            "Commit frontend-stable/build or install npm in deployment."
        )

    st.info("Frontend build not found. Building frontend bundle...")
    install = subprocess.run(
        [npm_bin, "ci", "--no-audit", "--no-fund"],
        cwd=str(FRONTEND_DIR),
        capture_output=True,
        text=True,
    )
    if install.returncode != 0:
        tail = "\n".join((install.stdout + "\n" + install.stderr).splitlines()[-40:])
        raise RuntimeError(f"npm ci failed:\n{tail}")

    build = subprocess.run(
        [npm_bin, "run", "build"],
        cwd=str(FRONTEND_DIR),
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        tail = "\n".join((build.stdout + "\n" + build.stderr).splitlines()[-60:])
        raise RuntimeError(f"npm run build failed:\n{tail}")

    if not manifest_path.exists():
        raise FileNotFoundError("Build completed but asset-manifest.json is still missing.")


def _render_local_frontend(api_base_url: str) -> None:
    _ensure_local_build()
    manifest_path = BUILD_DIR / "asset-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("frontend-stable/build/asset-manifest.json not found")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    css_rel = manifest.get("files", {}).get("main.css", "")
    js_rel = manifest.get("files", {}).get("main.js", "")
    if not css_rel or not js_rel:
        raise RuntimeError("Build manifest missing main.css or main.js")

    css_bundle = _read_build_asset(css_rel)
    js_bundle = _read_build_asset(js_rel)

    # Keep build immutable; patch API endpoint at runtime for Streamlit deployment.
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
    <script>{js_bundle}</script>
  </body>
</html>
"""
    components.html(html, height=1600, scrolling=True)


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
    _render_local_frontend(api_base_url)
except Exception as exc:
    st.error("Failed to render local frontend build in Streamlit.")
    st.code(str(exc))
