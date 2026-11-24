"""App settings, read from environment variables or backend/.env."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

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
    cors_origins: str = "http://localhost:5173"

    # Public-demo protection: AI calls (chat, explain, AI categorising) per hour per IP (0 = no limit),
    # and how often anyone may re-download market data.
    ai_requests_per_hour: int = 30
    market_refresh_min_minutes: int = 60

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_key.strip())


settings = Settings()
