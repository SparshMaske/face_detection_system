import json
import os
import re
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
STATIC_APP_DIR = ROOT_DIR / "static" / "visitor_app"


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
    install_cmds = [
        [npm_bin, "ci", "--no-audit", "--no-fund"],
        [npm_bin, "install", "--no-audit", "--no-fund"],
        [npm_bin, "install", "--no-audit", "--no-fund", "--legacy-peer-deps"],
    ]
    install_ok = False
    install_logs = []
    for cmd in install_cmds:
        step = subprocess.run(
            cmd,
            cwd=str(FRONTEND_DIR),
            capture_output=True,
            text=True,
        )
        if step.returncode == 0:
            install_ok = True
            break
        tail = "\n".join((step.stdout + "\n" + step.stderr).splitlines()[-30:])
        install_logs.append(f"{' '.join(cmd)} failed:\n{tail}")

    if not install_ok:
        raise RuntimeError("Frontend dependency install failed:\n\n" + "\n\n".join(install_logs))

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


def _prepare_static_frontend(api_base_url: str) -> None:
    _ensure_local_build()
    manifest_path = BUILD_DIR / "asset-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("frontend-stable/build/asset-manifest.json not found")

    marker = STATIC_APP_DIR / ".api_base_url"
    if marker.exists():
        current = marker.read_text(encoding="utf-8").strip()
        if current == api_base_url and (STATIC_APP_DIR / "index.html").exists():
            return

    if STATIC_APP_DIR.exists():
        shutil.rmtree(STATIC_APP_DIR)
    shutil.copytree(BUILD_DIR, STATIC_APP_DIR)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    css_rel = manifest.get("files", {}).get("main.css", "")
    js_rel = manifest.get("files", {}).get("main.js", "")
    if not css_rel or not js_rel:
        raise RuntimeError("Build manifest missing main.css or main.js")

    js_path = STATIC_APP_DIR / js_rel.lstrip("/")
    if not js_path.exists():
        raise FileNotFoundError(f"Main bundle not found: {js_path}")

    # Keep build immutable; patch API endpoint at runtime for Streamlit deployment.
    js_bundle = js_path.read_text(encoding="utf-8", errors="ignore")
    js_bundle = js_bundle.replace("http://127.0.0.1:5000/api", api_base_url)
    js_bundle = js_bundle.replace("http://localhost:5000/api", api_base_url)
    runtime_guard = (
        "(function(){"
        "function show(msg){"
        "try{"
        "var id='streamlit-runtime-guard';"
        "var el=document.getElementById(id);"
        "if(!el){el=document.createElement('pre');el.id=id;"
        "el.style.cssText='position:fixed;left:12px;right:12px;top:12px;z-index:2147483647;"
        "background:#2a1114;color:#fecaca;padding:12px;border-radius:8px;"
        "font:12px/1.4 monospace;white-space:pre-wrap;max-height:40vh;overflow:auto;';"
        "document.body.appendChild(el);}"
        "el.textContent=msg;"
        "}catch(_){}}"
        "window.addEventListener('error',function(e){show('Frontend runtime error: '+(e.message||'Unknown'));});"
        "window.addEventListener('unhandledrejection',function(e){show('Frontend unhandled rejection: '+String(e.reason||'Unknown'));});"
        "})();\n"
    )
    js_bundle = runtime_guard + js_bundle
    js_path.write_text(js_bundle, encoding="utf-8")

    index_path = STATIC_APP_DIR / "index.html"
    index_html = index_path.read_text(encoding="utf-8", errors="ignore")
    index_html = re.sub(r'href="/static/', 'href="./static/', index_html)
    index_html = re.sub(r'src="/static/', 'src="./static/', index_html)
    index_html = index_html.replace('href="/vite.svg"', 'href="./favicon.ico"')
    index_html = re.sub(r'<script[^>]+src="/src/main\.jsx"[^>]*></script>', '', index_html)
    index_path.write_text(index_html, encoding="utf-8")

    marker.write_text(api_base_url, encoding="utf-8")


def _render_static_frontend() -> None:
    html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Visitor Monitoring System</title>
    <style>
      html, body {
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
        background: #d7dce6;
        overflow: hidden;
      }
      #app-frame {
        border: 0;
        width: 100vw;
        height: 100vh;
        display: block;
      }
      #boot-error {
        display: none;
        margin: 12px;
        padding: 12px;
        border-radius: 8px;
        white-space: pre-wrap;
        background: #2a1114;
        color: #fecaca;
        font-family: monospace;
        font-size: 12px;
      }
    </style>
  </head>
  <body>
    <iframe id="app-frame" title="visitor-app" allow="camera; microphone"></iframe>
    <div id="boot-error"></div>
    <script>
      const frame = document.getElementById('app-frame');
      const err = document.getElementById('boot-error');

      function showError(msg) {
        err.style.display = 'block';
        err.textContent = msg;
      }

      const candidates = [
        '/app/static/visitor_app/index.html#/login',
        '/static/visitor_app/index.html#/login',
        './app/static/visitor_app/index.html#/login',
        './static/visitor_app/index.html#/login'
      ];

      (async () => {
        for (const url of candidates) {
          const probe = url.split('#')[0];
          try {
            const resp = await fetch(probe, { method: 'GET', cache: 'no-store' });
            if (resp.ok) {
              frame.src = url;
              return;
            }
          } catch (_) {
            // try next candidate
          }
        }
        showError('Unable to load static frontend index.html from Streamlit static paths.');
      })();
    </script>
  </body>
</html>
"""
    components.html(html, height=1000, scrolling=False)


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
    _prepare_static_frontend(api_base_url)
    _render_static_frontend()
except Exception as exc:
    st.error("Failed to render local frontend build in Streamlit.")
    st.code(str(exc))
