"""Request dependencies shared by the routes."""
import re

from fastapi import Header, HTTPException, Request

from app.config import settings
from app.ratelimit import RateLimiter

_CLIENT_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_ai_limiter = RateLimiter(settings.ai_requests_per_hour, window_seconds=3600)


def client_id(x_client_id: str | None = Header(default=None)) -> str:
    """The visitor's id from the `X-Client-Id` header (the browser makes a random one).
    Requests without it, such as curl or /docs, share the id "local"."""
    if x_client_id is None:
        return "local"
    if not _CLIENT_ID.match(x_client_id):
        raise HTTPException(400, "Invalid X-Client-Id header")
    return x_client_id


def _ip(request: Request) -> str:
    """Caller's IP. Behind a host's proxy (Render) the real one is first in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")


def ai_rate_limit(request: Request) -> None:
    """Protects the Gemini quota on the public demo: N AI calls per hour per IP address."""
    if not _ai_limiter.allow(_ip(request)):
        raise HTTPException(429, f"AI limit reached ({settings.ai_requests_per_hour} requests an hour). Try again later.")
