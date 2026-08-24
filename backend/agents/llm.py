"""LLM access for the Diagnosis and Decision nodes — plain HTTP, no provider SDK.

If neither OPENAI_API_KEY nor ANTHROPIC_API_KEY is set, `complete_json()` returns None
and callers fall back to a deterministic heuristic. This keeps the whole pipeline
runnable offline for dev/rehearsal, and makes the fallback an explicit, visible code
path rather than a silent failure.
"""

import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def complete_json(system_prompt: str, user_prompt: str) -> dict | None:
    if settings.OPENAI_API_KEY:
        return _openai_json(system_prompt, user_prompt)
    if settings.ANTHROPIC_API_KEY:
        return _anthropic_json(system_prompt, user_prompt)
    return None


def _openai_json(system_prompt: str, user_prompt: str) -> dict | None:
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={
                "model": settings.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            },
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        logger.exception("OpenAI diagnosis/decision call failed — falling back to heuristic")
        return None


def _anthropic_json(system_prompt: str, user_prompt: str) -> dict | None:
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 512,
                "system": system_prompt + "\nRespond with JSON only, no prose.",
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
        return json.loads(content)
    except Exception:
        logger.exception("Anthropic diagnosis/decision call failed — falling back to heuristic")
        return None
