"""App settings, from environment variables, a `.env` file in the project root, or Streamlit secrets."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # Free key from https://aistudio.google.com/apikey. Without it the app still works,
    # and every AI feature falls back to a rule-based answer.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    # Tried in order when the main model is overloaded (503), times out (504) or is rate-limited (429).
    gemini_fallback_models: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: int = 45
    embedding_model: str = "gemini-embedding-001"

    database_url: str = f"sqlite:///{(DATA_DIR / 'wealthwise.db').as_posix()}"
    risk_free_rate: float = 0.065  # roughly India's 91-day T-bill yield, used in Sharpe / Sortino

    # Public-demo protection for the Gemini quota: AI calls (chat, explain, AI categorising) per hour,
    # per visitor and for the whole app (0 = no limit); and how often market data may be re-downloaded.
    ai_requests_per_hour: int = 20
    ai_requests_per_hour_total: int = 300
    market_refresh_min_minutes: int = 60

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_key.strip())


def _from_streamlit_secrets(s: Settings) -> Settings:
    """On Streamlit Community Cloud the key is set in the app's Secrets box, not in a .env file."""
    if s.gemini_api_key:
        return s
    try:
        import streamlit as st
        key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:  # no secrets file, or not running under Streamlit
        key = ""
    return s.model_copy(update={"gemini_api_key": key}) if key else s


settings = _from_streamlit_secrets(Settings())
