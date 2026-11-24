"""Thin wrapper around the Google Gemini SDK (`google-genai`)."""
import logging
from functools import lru_cache

from google import genai
from google.genai import errors, types

from app.config import settings

log = logging.getLogger(__name__)
BUSY_CODES = {429, 503, 504}  # rate-limited, overloaded, timed out: worth trying another model


class AIUnavailable(RuntimeError):
    """Raised when no GEMINI_API_KEY is set; callers fall back to rule-based output."""


@lru_cache
def client() -> genai.Client:
    if not settings.ai_enabled:
        raise AIUnavailable("Set GEMINI_API_KEY in backend/.env to enable AI features.")
    return genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(
        timeout=settings.gemini_timeout_seconds * 1000,
        retry_options=types.HttpRetryOptions(attempts=2)))  # fail fast; we fall back to another model instead


def models() -> list[str]:
    fallbacks = [m.strip() for m in settings.gemini_fallback_models.split(",") if m.strip()]
    return [settings.gemini_model, *fallbacks]


def generate(contents, system: str, *, tools=None, json_schema=None, temperature: float = 0.3):
    """One model call. `tools` are plain Python functions (their signature and docstring become the
    tool schema); they are *not* called automatically, so the agent loop stays in our code.
    If the main model is busy, the fallback models are tried in order."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True) if tools else None,
        response_mime_type="application/json" if json_schema else None,
        response_schema=json_schema,
    )
    candidates = models()
    for i, model in enumerate(candidates):
        try:
            return client().models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as e:
            if e.code not in BUSY_CODES or i == len(candidates) - 1:
                raise
            log.warning("%s unavailable (%s), trying %s", model, e.code, candidates[i + 1])


def embed(texts: list[str], task: str) -> list[list[float]]:
    """Embed texts in batches. `task` is RETRIEVAL_DOCUMENT or RETRIEVAL_QUERY."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), 50):
        resp = client().models.embed_content(
            model=settings.embedding_model, contents=texts[start:start + 50],
            config=types.EmbedContentConfig(task_type=task, output_dimensionality=768))
        vectors.extend(e.values for e in resp.embeddings)
    return vectors
