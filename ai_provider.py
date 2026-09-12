"""
AI Provider abstraction layer.

LaMa AI does not lock itself to a single LLM vendor. This module exposes one
function, `generate()`, that the rest of the backend calls. Internally it
picks whichever provider is configured via environment variables. If nothing
is configured (no API key), the caller is expected to fall back to the local
knowledge-base engine in `lama_engine.py` — this module simply signals that
no external provider is available.

Supported providers (set AI_PROVIDER in .env):
  - "anthropic"  (ANTHROPIC_API_KEY)
  - "openai"     (OPENAI_API_KEY)
  - "none"       (default — local knowledge base only)
"""
import os
import json
from typing import Optional

AI_PROVIDER = os.getenv("AI_PROVIDER", "none").lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_client_cache = {}


def provider_available() -> bool:
    """True if a real external AI provider is configured and usable."""
    if AI_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return True
    if AI_PROVIDER == "openai" and OPENAI_API_KEY:
        return True
    return False


def _anthropic_generate(system_prompt: str, user_message: str, max_tokens: int) -> str:
    import anthropic  # imported lazily so the package is optional

    if "anthropic" not in _client_cache:
        _client_cache["anthropic"] = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    client = _client_cache["anthropic"]
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    return "".join(parts).strip()


def _openai_generate(system_prompt: str, user_message: str, max_tokens: int) -> str:
    import openai  # imported lazily so the package is optional

    if "openai" not in _client_cache:
        _client_cache["openai"] = openai.OpenAI(api_key=OPENAI_API_KEY)
    client = _client_cache["openai"]
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def generate(system_prompt: str, user_message: str, max_tokens: int = 800) -> Optional[str]:
    """
    Calls the configured external AI provider. Returns None (never raises for
    "not configured") if no provider is set up, so callers can fall back to
    the local knowledge-base engine. Raises only for genuine provider errors
    (network issues, bad key, etc.) so the caller can report a clean error.
    """
    if AI_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return _anthropic_generate(system_prompt, user_message, max_tokens)
    if AI_PROVIDER == "openai" and OPENAI_API_KEY:
        return _openai_generate(system_prompt, user_message, max_tokens)
    return None


def generate_json(system_prompt: str, user_message: str, max_tokens: int = 1200) -> Optional[dict]:
    """Same as generate(), but expects (and parses) a JSON object response."""
    raw = generate(system_prompt, user_message, max_tokens=max_tokens)
    if raw is None:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                return None
        return None
