"""Wealth Wise: AI-powered personal finance assistant.

Run:  streamlit run streamlit_app.py
"""
import streamlit as st

from app_pages.common import setup
from wealthwise.config import settings
from wealthwise.rag.knowledge import get_knowledge_base

st.set_page_config(page_title="Wealth Wise", page_icon="📈", layout="wide")
setup()

pages = st.navigation({
    "": [st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/home:", default=True)],
    "Invest": [
        st.Page("app_pages/plan.py", title="My Plan", icon=":material/insights:", url_path="plan"),
        st.Page("app_pages/profile.py", title="Profile", icon=":material/person:", url_path="profile"),
    ],
    "Money": [st.Page("app_pages/expenses.py", title="Expenses", icon=":material/receipt_long:", url_path="expenses")],
    "Learn": [
        st.Page("app_pages/assistant.py", title="Assistant", icon=":material/chat:", url_path="assistant"),
        st.Page("app_pages/learn.py", title="Lessons", icon=":material/school:", url_path="learn"),
    ],
})

with st.sidebar:
    st.caption(f"{'🟢 Gemini AI on' if settings.ai_enabled else '⚪ AI off (no GEMINI_API_KEY)'} · "
               f"lesson search: {get_knowledge_base().mode}")
    st.caption("Educational project, not SEBI-registered investment advice.")

pages.run()
