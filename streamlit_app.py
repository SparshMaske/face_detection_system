import os
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


def _query_param(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        return value[0] if value else ""
    return str(value)


def _secret_value(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        return ""
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return str(value).strip()


def _is_streamlit_cloud() -> bool:
    truthy = {"1", "true", "yes", "on"}
    return (
        os.getenv("STREAMLIT_SHARING_MODE", "").strip().lower() in truthy
        or os.getenv("IS_STREAMLIT_CLOUD", "").strip().lower() in truthy
    )


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


query_app = _query_param("app").strip()
secret_app = _secret_value("STREAMLIT_EMBED_URL")
if not secret_app:
    secret_app = _secret_value("FRONTEND_URL")
if not secret_app:
    secret_app = _secret_value("APP_URL")
env_app = os.getenv("STREAMLIT_EMBED_URL", "").strip()
if not env_app:
    env_app = os.getenv("FRONTEND_URL", "").strip()
if not env_app:
    env_app = os.getenv("APP_URL", "").strip()
embed_url = query_app or secret_app or env_app
is_cloud = _is_streamlit_cloud()

if query_app:
    st.info(f"Using app URL from query param: {query_app}")
elif secret_app:
    st.info("Using app URL from Streamlit secrets.")
elif env_app:
    st.info("Using app URL from environment variable.")

if not embed_url:
    st.error("Missing hosted frontend URL for Streamlit Cloud deployment.")
    manual_url = st.text_input(
        "Frontend URL",
        value="",
        placeholder="https://your-frontend-url",
    ).strip()
    if st.button("Open App"):
        if _is_http_url(manual_url):
            st.query_params["app"] = manual_url
            st.rerun()
        else:
            st.error("Please enter a valid URL (http/https).")
    st.markdown(
        """
        Set your frontend URL using one of these:
        - Streamlit Cloud Secrets: `STREAMLIT_EMBED_URL="https://your-frontend-url"`
        - Streamlit Cloud Secrets: `FRONTEND_URL="https://your-frontend-url"`
        - Streamlit Cloud env var: `STREAMLIT_EMBED_URL=https://your-frontend-url`
        - Query param: `?app=https://your-frontend-url`

        Local development example:
        `STREAMLIT_EMBED_URL=http://localhost:3000 streamlit run streamlit_app.py`

        Example:
        `https://your-streamlit-app.streamlit.app/?app=https://your-frontend-url`
        """
    )
    st.stop()

if not _is_http_url(embed_url):
    st.error("Invalid frontend URL. Use a full URL such as `https://your-frontend-url`.")
    st.stop()

if is_cloud and embed_url.startswith("http://"):
    st.warning("Streamlit Cloud is HTTPS. Use an `https://` frontend URL to avoid browser blocking.")

components.iframe(embed_url, height=1200, scrolling=True)
