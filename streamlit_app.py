import os

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


query_app = _query_param("app").strip()
env_app = os.getenv("STREAMLIT_EMBED_URL", "").strip()
default_local_app = "http://localhost:3000"
embed_url = query_app or env_app or default_local_app

if query_app:
    st.info(f"Using app URL from query param: {query_app}")
elif env_app:
    st.info(f"Using app URL from STREAMLIT_EMBED_URL: {env_app}")
else:
    st.warning(
        "No app URL provided. Defaulting to `http://localhost:3000`. "
        "Use `?app=<url>` or set `STREAMLIT_EMBED_URL` to override."
    )

if not (query_app or env_app):
    st.markdown(
        """
        For a shareable Streamlit Cloud deployment, set your hosted frontend URL using one of these:
        - Streamlit Cloud secret/env: `STREAMLIT_EMBED_URL=https://your-frontend-url`
        - Query param: `?app=https://your-frontend-url`

        Example:
        `https://your-streamlit-app.streamlit.app/?app=https://your-frontend-url`
        """
    )

components.iframe(embed_url, height=1200, scrolling=True)
