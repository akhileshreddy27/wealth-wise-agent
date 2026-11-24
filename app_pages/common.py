"""Shared helpers for the Streamlit pages: the visitor id, database access, AI rate limits, formatting."""
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime

import streamlit as st

from wealthwise.config import settings
from wealthwise.db import SessionLocal, init_db
from wealthwise.expenses.analytics import inr  # noqa: F401  (re-exported for the pages)
from wealthwise.rag.knowledge import get_knowledge_base
from wealthwise.ratelimit import RateLimiter

_VISITOR = re.compile(r"^[a-f0-9]{32}$")


@st.cache_resource
def setup() -> bool:
    """Runs once per server: create tables, and build the lesson index in the background."""
    init_db()
    threading.Thread(target=get_knowledge_base, daemon=True).start()
    return True


def visitor_id() -> str:
    """Each visitor gets a random id, kept in the URL (`?u=...`) so a refresh keeps their data.
    Everything they save belongs to this id, so visitors never see each other's data."""
    if "visitor" not in st.session_state:
        from_url = st.query_params.get("u", "")
        st.session_state.visitor = from_url if _VISITOR.match(from_url) else uuid.uuid4().hex
    st.query_params["u"] = st.session_state.visitor  # page switches clear query params, so set it every run
    return st.session_state.visitor


@contextmanager
def db_session():
    with SessionLocal() as db:
        yield db


# ---------- AI rate limits (shared by all visitors of this server) ----------

@st.cache_resource
def _limiters() -> tuple[RateLimiter, RateLimiter]:
    return (RateLimiter(settings.ai_requests_per_hour, 3600), RateLimiter(settings.ai_requests_per_hour_total, 3600))


def allow_ai_call() -> bool:
    """False (with a message shown) once this visitor or the whole app hits its hourly AI limit."""
    per_visitor, total = _limiters()
    if not per_visitor.allow(visitor_id()):
        st.warning(f"You've reached the demo limit of {settings.ai_requests_per_hour} AI requests an hour. "
                   "Please try again later.")
        return False
    if not total.allow("all"):
        st.warning("The demo has reached its hourly AI limit. Please try again in a while.")
        return False
    return True


# ---------- layout ----------

def metric_row(*metrics: dict) -> None:
    """Metric cards that wrap onto a second row on narrow screens instead of truncating their values."""
    with st.container(horizontal=True, gap="small"):
        for m in metrics:
            st.metric(**({"delta_color": "off", "delta_arrow": "off"} | m), border=True, width=230)


# ---------- formatting ----------

def inr_compact(n: float | None) -> str:
    """₹1.20 Cr, ₹4.50 L, ₹12,500."""
    if n is None:
        return "–"
    if abs(n) >= 1e7:
        return f"₹{n / 1e7:.2f} Cr"
    if abs(n) >= 1e5:
        return f"₹{n / 1e5:.2f} L"
    return inr(n)


def pct(x: float | None, digits: int = 1) -> str:
    return "–" if x is None else f"{x * 100:.{digits}f}%"


def month_label(month: str) -> str:
    return datetime.strptime(month, "%Y-%m").strftime("%b %Y")


def ago(iso: str | None) -> str:
    if not iso:
        return "never"
    minutes = (datetime.now().astimezone() - datetime.fromisoformat(iso)).total_seconds() / 60
    if minutes < 60:
        return f"{minutes:.0f} min ago"
    return f"{minutes / 60:.0f} h ago" if minutes < 1440 else f"{minutes / 1440:.0f} days ago"


ASSET_COLORS = {"Equity": "#059669", "Debt funds": "#6366f1", "Fixed deposits": "#f59e0b", "Liquid": "#0ea5e9"}
ASSET_LABELS = {"equity": "Equity", "debt": "Debt funds", "fd": "Fixed deposits", "liquid": "Liquid"}
