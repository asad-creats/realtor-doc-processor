"""
Cloud LLM client (OpenAI-compatible chat completions).

This replaces the old local-Ollama dependency. It talks to a hosted provider
over HTTPS — Groq by default — exactly like the TC Command Center backend's
AI router. No GPU, no local daemon, deployable on any plain cloud host.

Configuration (env vars):
    AI_PROVIDER   groq | openrouter | openai   (default: groq)
    AI_MODEL      override the model id          (default: per-provider below)
    AI_ENDPOINT   override the full chat endpoint (advanced)
    AI_API_KEY    generic key (used if the provider-specific one is unset)
    GROQ_API_KEY / OPENROUTER_API_KEY / OPENAI_API_KEY

Groq free tier is plenty for testing; `llama-3.3-70b-versatile` returns clean
JSON and is fast.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx


class LLMError(RuntimeError):
    """Raised when the LLM call fails or the provider isn't configured."""


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


def _config() -> tuple[str, str, Optional[str], str]:
    """Resolve (provider, endpoint, api_key, default_model) from the env."""
    provider = os.getenv("AI_PROVIDER", "groq").strip().lower()
    endpoint, key_env, default_model = _PRESETS.get(provider, _PRESETS["groq"])
    endpoint = os.getenv("AI_ENDPOINT", endpoint)
    api_key = os.getenv(key_env) or os.getenv("AI_API_KEY")
    model = os.getenv("AI_MODEL") or default_model
    return provider, endpoint, api_key, model


def is_configured() -> bool:
    """True if an API key is available for the selected provider."""
    return bool(_config()[2])


def provider_name() -> str:
    return _config()[0]


def active_model(override: Optional[str] = None) -> str:
    return override or _config()[3]


def chat_json(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 4000,
    timeout: float = 90.0,
) -> str:
    """
    Send a system+user prompt and return the assistant's text.

    Requests JSON output (response_format=json_object) so the classifier gets
    parseable output. Raises LLMError with a clear message on any failure.
    """
    provider, endpoint, api_key, default_model = _config()
    if not api_key:
        raise LLMError(
            f"No API key for provider '{provider}'. Set the {provider.upper()}_API_KEY "
            f"environment variable (or AI_API_KEY)."
        )
    model = model or default_model

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = httpx.post(endpoint, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as e:
        raise LLMError(f"{provider} network error: {e}") from e

    if resp.status_code >= 400:
        # Surface the provider's message; common cases: 401 bad key, 429 quota.
        try:
            body = resp.json()
            msg = (body.get("error") or {}).get("message") or resp.text[:300]
        except ValueError:
            msg = resp.text[:300]
        raise LLMError(f"{provider} HTTP {resp.status_code}: {msg}")

    try:
        data = resp.json()
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (ValueError, KeyError, IndexError) as e:
        raise LLMError(f"{provider} returned an unexpected response: {e}") from e
