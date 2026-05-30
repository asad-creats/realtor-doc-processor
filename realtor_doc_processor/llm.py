"""
Cloud LLM client (OpenAI-compatible chat completions) with retries + fallback.

Talks to a hosted provider over HTTPS. Default is Groq. If a call is
rate-limited, errors, or returns junk, it retries with backoff and then falls
back to any other configured provider (OpenRouter / OpenAI), so a single flaky
response doesn't fail the whole job.

Configuration (env vars):
    AI_PROVIDER   groq | openrouter | openai   (default: groq) — tried first
    AI_MODEL      override the primary model id (optional)
    AI_ENDPOINT   override the full chat endpoint (advanced)
    AI_API_KEY    generic key (used if the provider-specific one is unset)
    GROQ_API_KEY / OPENROUTER_API_KEY / OPENAI_API_KEY

Any provider with a key set becomes part of the fallback chain automatically.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when all providers/retries are exhausted, or none is configured."""


# provider -> (endpoint, api-key env var, default model)
_PRESETS = {
    "groq": (
        "https://api.groq.com/openai/v1/chat/completions",
        "GROQ_API_KEY",
        "llama-3.3-70b-versatile",
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1/chat/completions",
        "OPENROUTER_API_KEY",
        "openai/gpt-oss-120b:free",
    ),
    "openai": (
        "https://api.openai.com/v1/chat/completions",
        "OPENAI_API_KEY",
        "gpt-4o-mini",
    ),
}

MAX_RETRIES = 2          # per provider, on transient errors
BACKOFF_BASE = 1.5       # seconds

# Vision-capable model per provider (used when images are sent).
_VISION_MODELS = {
    "groq": "meta-llama/llama-4-scout-17b-16e-instruct",
    "openrouter": "qwen/qwen-2.5-vl-72b-instruct:free",
    "openai": "gpt-4o-mini",
}


def _key_for(provider: str) -> Optional[str]:
    _, key_env, _ = _PRESETS[provider]
    return os.getenv(key_env) or os.getenv("AI_API_KEY")


def _primary() -> str:
    return os.getenv("AI_PROVIDER", "groq").strip().lower()


def _providers_to_try() -> list[str]:
    """Primary first, then any other provider that has a key configured."""
    primary = _primary()
    order = [primary] + [p for p in _PRESETS if p != primary]
    return [p for p in order if p in _PRESETS and _key_for(p)]


def is_configured() -> bool:
    return bool(_providers_to_try())


def provider_name() -> str:
    return _primary()


def active_model(override: Optional[str] = None) -> str:
    if override:
        return override
    env_model = os.getenv("AI_MODEL")
    if env_model:
        return env_model
    primary = _primary()
    return _PRESETS.get(primary, _PRESETS["groq"])[2]


def _model_for(provider: str, requested: Optional[str]) -> str:
    """Use the requested model only for the primary provider (model ids are
    provider-specific); fallback providers use their own default."""
    if provider == _primary():
        return requested or active_model()
    return _PRESETS[provider][2]


class _Transient(Exception):
    pass


class _Fatal(Exception):
    pass


def _post(provider: str, model: str, system_prompt: str, user_prompt: str,
          temperature: float, max_tokens: int, timeout: float,
          images: Optional[list] = None) -> str:
    endpoint, _, _ = _PRESETS[provider]
    api_key = _key_for(provider)

    if images:
        # OpenAI-style multimodal: content is a list of text + image_url parts.
        import base64
        parts = [{"type": "text", "text": user_prompt}]
        for mime, data in images:
            b64 = base64.b64encode(data).decode("ascii")
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:{mime};base64,{b64}"}})
        user_content = parts
    else:
        user_content = user_prompt

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        resp = httpx.post(endpoint, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as e:
        raise _Transient(f"{provider} network error: {e}")

    if resp.status_code == 429 or resp.status_code >= 500:
        raise _Transient(f"{provider} HTTP {resp.status_code}")
    if resp.status_code >= 400:
        try:
            msg = (resp.json().get("error") or {}).get("message") or resp.text[:200]
        except ValueError:
            msg = resp.text[:200]
        raise _Fatal(f"{provider} HTTP {resp.status_code}: {msg}")

    try:
        data = resp.json()
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (ValueError, KeyError, IndexError) as e:
        raise _Transient(f"{provider} bad response shape: {e}")


def chat_json(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 4000,
    timeout: float = 90.0,
) -> str:
    """
    Send a system+user prompt and return the assistant's text (JSON requested).

    Tries the primary provider with retries, then falls back to any other
    configured provider. Raises LLMError only if everything fails.
    """
    providers = _providers_to_try()
    if not providers:
        raise LLMError(
            f"No API key for provider '{_primary()}'. Set the "
            f"{_primary().upper()}_API_KEY environment variable."
        )

    errors: list[str] = []
    for provider in providers:
        m = _model_for(provider, model)
        for attempt in range(MAX_RETRIES + 1):
            try:
                return _post(provider, m, system_prompt, user_prompt,
                             temperature, max_tokens, timeout)
            except _Transient as e:
                errors.append(f"{e} (try {attempt + 1})")
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE * (attempt + 1))
                    continue
                logger.warning("Provider %s exhausted retries; falling back.", provider)
            except _Fatal as e:
                errors.append(str(e))
                logger.warning("Provider %s fatal error; falling back.", provider)
                break  # don't retry fatal errors on same provider

    raise LLMError("All providers failed: " + " | ".join(errors[-4:]))


def vision_model(provider: Optional[str] = None) -> str:
    provider = provider or _primary()
    return os.getenv("VISION_MODEL") or _VISION_MODELS.get(provider, _VISION_MODELS["groq"])


def vision_json(
    system_prompt: str,
    user_prompt: str,
    images: list,                       # list of (mime_type, raw_bytes)
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 1200,
    timeout: float = 120.0,
) -> str:
    """Same as chat_json but sends page images to a vision-capable model."""
    providers = _providers_to_try()
    if not providers:
        raise LLMError(f"No API key for provider '{_primary()}'.")

    errors: list[str] = []
    for provider in providers:
        m = model if (model and provider == _primary()) else vision_model(provider)
        for attempt in range(MAX_RETRIES + 1):
            try:
                return _post(provider, m, system_prompt, user_prompt,
                             temperature, max_tokens, timeout, images=images)
            except _Transient as e:
                errors.append(f"{e} (try {attempt + 1})")
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE * (attempt + 1))
                    continue
            except _Fatal as e:
                errors.append(str(e))
                break

    raise LLMError("All vision providers failed: " + " | ".join(errors[-4:]))
