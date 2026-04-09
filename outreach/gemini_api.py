"""Minimal Gemini (Google AI Studio) REST client.

We use the Generative Language API `generateContent` endpoint with an API key.
No extra dependencies beyond httpx.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class GeminiResult:
    text: str
    raw_json: dict | list | str | None = None


def _parse_retry_delay(response_text: str, default: float = 15.0) -> float:
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", response_text, flags=re.I)
    if m:
        return min(float(m.group(1)) + 2.0, 90.0)
    return default


def _endpoint_for_model(model: str) -> str:
    m = (model or "").strip()
    if not m:
        m = "gemini-2.0-flash"
    if m.startswith("models/"):
        m = m[len("models/") :]
    return f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"


def gemini_generate_text(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.6,
    max_output_tokens: int = 2048,
    timeout_sec: float = 60.0,
) -> GeminiResult:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    url = _endpoint_for_model(model or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"))
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": float(temperature),
            "maxOutputTokens": int(max_output_tokens),
        },
    }
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    max_retries = 3
    r = None
    for attempt in range(max_retries):
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(url, headers=headers, json=payload)
        if r.status_code == 429 or r.status_code == 503:
            wait = _parse_retry_delay(r.text, default=15.0 * (attempt + 1))
            time.sleep(wait)
            continue
        break
    assert r is not None
    if not r.is_success:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:800]}")
    try:
        data = r.json()
    except json.JSONDecodeError:
        return GeminiResult(text=r.text or "", raw_json=r.text)

    text_parts: list[str] = []
    try:
        candidates = data.get("candidates") if isinstance(data, dict) else None
        if isinstance(candidates, list) and candidates:
            content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
            parts = content.get("parts") if isinstance(content, dict) else None
            if isinstance(parts, list):
                for p in parts:
                    if isinstance(p, dict) and isinstance(p.get("text"), str):
                        text_parts.append(p["text"])
    except Exception:
        text_parts = []

    return GeminiResult(text="".join(text_parts).strip(), raw_json=data)

