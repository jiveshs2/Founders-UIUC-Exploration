from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from outreach.env_loader import groq_key_missing_message, load_environment
from outreach.models import ExtractResult, LeadRow

MAX_CHARS = 120_000


def normalize_page_url(url: str) -> str:
    """Ensure httpx gets an absolute URL with a scheme (common mistake: ycombinator.com without https://)."""
    u = (url or "").strip()
    if not u:
        raise ValueError("URL is empty")
    if u.startswith("//"):
        u = "https:" + u
    elif not u.startswith(("http://", "https://")):
        u = "https://" + u

    parsed = urlparse(u)
    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError(
            "URL must include a hostname, e.g. https://www.ycombinator.com/companies"
        )
    hl = host.lower()
    if hl == "..." or all(c == "." for c in hl):
        raise ValueError(
            "You used the literal text '...' as --url. Replace it with the real page link (copy from your browser)."
        )
    return u


def _main_text(html: str) -> str:
    try:
        from readability import Document

        doc = Document(html)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "lxml")
        return soup.get_text(separator="\n", strip=True)
    except Exception:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)


def fetch_page_text(url: str) -> str:
    url = normalize_page_url(url)
    headers = {
        "User-Agent": "OutreachAutomation/0.1 (research; contact: local)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            text = _main_text(r.text)
    except UnicodeError as e:
        raise ValueError(
            f"Invalid hostname in URL {url!r}. Use a real domain (paste the full address from your browser)."
        ) from e
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[truncated]"
    return text


def _parse_json_array(raw: str) -> list[dict]:
    raw = raw.strip()
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        raw = m.group(0)
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Model output is not a JSON array")
    return [x for x in data if isinstance(x, dict)]


def extract_rows_with_groq(
    page_text: str,
    extract_prompt: str,
    source_url: str,
    model: str | None = None,
) -> ExtractResult:
    from groq import Groq

    load_environment()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(groq_key_missing_message())
    model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    system = """You extract structured data for a spreadsheet. Output ONLY a valid JSON array of objects.
Each object MUST use these string keys when applicable: founder_name, company_name, batch, company_website, notes.
Use empty string "" for unknown fields. company_website should be a full URL when possible.
Do not include markdown fences or commentary."""

    user = f"""Source page URL: {source_url}

Instructions for what to extract:
{extract_prompt}

Page text:
---
{page_text}
---

Return a JSON array only."""

    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=16_384,
    )
    raw_text = completion.choices[0].message.content or ""
    try:
        items = _parse_json_array(raw_text)
    except (json.JSONDecodeError, ValueError) as e:
        return ExtractResult(rows=[], raw_model_text=raw_text + f"\n\n[parse error: {e}]")

    rows: list[LeadRow] = []
    for item in items:
        try:
            rows.append(LeadRow.model_validate(item))
        except Exception:
            rows.append(
                LeadRow(
                    founder_name=str(item.get("founder_name", "") or ""),
                    company_name=str(item.get("company_name", "") or ""),
                    batch=str(item.get("batch", "") or ""),
                    company_website=str(item.get("company_website", "") or ""),
                    notes=str(item.get("notes", "") or ""),
                )
            )
    return ExtractResult(rows=rows, raw_model_text=raw_text)
