from __future__ import annotations

import json
import os
import re

from outreach.env_loader import groq_key_missing_message, load_environment
from outreach.models import LeadRow
from outreach.prompts import build_generation_system_prompt


def _truncate_to_word_limit(text: str, max_words: int | None) -> str:
    """Trim to max_words at the nearest sentence boundary when possible."""
    limit = max_words if isinstance(max_words, int) and max_words > 0 else 100
    words = (text or "").strip().split()
    if len(words) <= limit:
        return (text or "").strip()

    # Try to cut at a sentence-ending punctuation near the limit.
    candidate = " ".join(words[:limit])
    # Walk backwards from the limit to find the last sentence end.
    for i in range(len(candidate) - 1, max(0, len(candidate) - 120), -1):
        if candidate[i] in ".!?" and (i + 1 >= len(candidate) or candidate[i + 1] in " \n\r"):
            return candidate[: i + 1].strip()

    # No clean sentence break found — just trim at the word boundary and add ellipsis.
    return candidate.rstrip("., ") + "…"


def _format_body_paragraphs(text: str) -> str:
    """Ensure a blank line after greeting; keep output readable."""
    s = (text or "").strip()
    if not s:
        return s

    # Normalize newlines
    s = s.replace("\r\n", "\n").replace("\r", "\n")

    # If greeting is the first line, ensure a blank line after it.
    first_line, sep, rest = s.partition("\n")
    fl = first_line.strip()
    if re.match(r"^(dear|hi|hello)\b.*[,!]$", fl, flags=re.I):
        rest = rest.lstrip("\n")
        if rest and not rest.startswith("\n"):
            s = fl + "\n\n" + rest
        else:
            s = fl + "\n\n" + rest.lstrip("\n")

    # If everything is one long paragraph, do a light split after sentences.
    if "\n" not in s and len(s) > 240:
        s = re.sub(r"([.!?])\s+(?=[A-Z])", r"\1\n\n", s)

    # Collapse excessive blank lines.
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def _normalize_sign_off(sign_off: str) -> str:
    s = (sign_off or "").strip()
    if not s:
        return ""
    # Support users pasting literal "\n" sequences.
    s = s.replace("\\r\\n", "\n").replace("\\n", "\n")
    return s.strip()


def _parse_outreach_jsonish(raw: str) -> tuple[str, str]:
    """Tolerant parser for model outputs that are near-JSON but not strict JSON."""
    m = re.search(r'"subject"\s*:\s*"([^"]+)"', raw, flags=re.I | re.S)
    subj = m.group(1).strip() if m else "Follow-up"
    m2 = re.search(r'"body"\s*:\s*"([\s\S]*?)"\s*\}?$', raw, flags=re.I)
    if m2:
        body = m2.group(1)
        body = body.replace('\\"', '"').replace("\\n", "\n").replace("\\r", "")
        return subj, body.strip()
    raise ValueError("could not parse json-ish response")


def _parse_outreach_json(raw: str) -> tuple[str, str]:
    raw = raw.strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    subj = str(data.get("subject", "") or "").strip()
    body = str(data.get("body", "") or "").strip()
    return subj, body


def generate_outreach_groq(
    row: LeadRow,
    purpose_prompt: str,
    model: str | None = None,
    sign_off: str = "",
    max_words: int | None = None,
) -> tuple[str, str]:
    from groq import Groq

    load_environment()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(groq_key_missing_message())
    model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    ctx = {
        "company_name": row.company_name,
        "founder_name": row.founder_name,
        "industry": row.industry,
        "company_website": row.company_website,
        "email": row.email or "",
        "notes": row.notes,
    }

    word_cap = max_words if isinstance(max_words, int) and max_words > 0 else 100
    system = build_generation_system_prompt()

    user = f"""Use the following instructions and lead data to write one email.
The email body MUST be a complete message of {word_cap} words or fewer. Do NOT exceed this limit. Finish every sentence — never cut off mid-sentence.

{purpose_prompt}

Lead (JSON):
{json.dumps(ctx, ensure_ascii=False)}

If the email address is missing, still write the body with an appropriate greeting using the founder or company name when known."""

    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.6,
        max_tokens=2048,
    )
    choice0 = completion.choices[0] if completion.choices else None
    raw_text = (choice0.message.content if choice0 and choice0.message else "") or ""
    so = _normalize_sign_off(sign_off)
    try:
        subj, body = _parse_outreach_json(raw_text)
        if so:
            body = (body.rstrip() + "\n\n" + so).strip()
        body = _format_body_paragraphs(body)
        return subj, _truncate_to_word_limit(body, max_words)
    except (json.JSONDecodeError, ValueError):
        try:
            subj, body = _parse_outreach_jsonish(raw_text)
        except ValueError:
            subj, body = "Follow-up", raw_text.strip() or "(empty model response)"
        if so:
            body = (body.rstrip() + "\n\n" + so).strip()
        body = _format_body_paragraphs(body)
        return subj, _truncate_to_word_limit(body, max_words)


def generate_outreach_gemini(
    row: LeadRow,
    purpose_prompt: str,
    model: str | None = None,
    sign_off: str = "",
    max_words: int | None = None,
) -> tuple[str, str]:
    load_environment()
    from outreach.gemini_api import gemini_generate_text

    ctx = {
        "company_name": row.company_name,
        "founder_name": row.founder_name,
        "industry": row.industry,
        "company_website": row.company_website,
        "email": row.email or "",
        "notes": row.notes,
    }

    word_cap = max_words if isinstance(max_words, int) and max_words > 0 else 100
    system = build_generation_system_prompt()
    user = f"""Use the following instructions and lead data to write one email.
The email body MUST be a complete message of {word_cap} words or fewer. Do NOT exceed this limit. Finish every sentence — never cut off mid-sentence.

{purpose_prompt}

Lead (JSON):
{json.dumps(ctx, ensure_ascii=False)}

If the email address is missing, still write the body with an appropriate greeting using the founder or company name when known."""

    res = gemini_generate_text(
        system=system,
        user=user,
        model=model,
        temperature=0.6,
        max_output_tokens=2048,
        timeout_sec=75.0,
    )
    raw_text = res.text or ""
    so = _normalize_sign_off(sign_off)
    try:
        subj, body = _parse_outreach_json(raw_text)
        if so:
            body = (body.rstrip() + "\n\n" + so).strip()
        body = _format_body_paragraphs(body)
        return subj, _truncate_to_word_limit(body, max_words)
    except (json.JSONDecodeError, ValueError):
        try:
            subj, body = _parse_outreach_jsonish(raw_text)
        except ValueError:
            subj, body = "Follow-up", raw_text.strip() or "(empty model response)"
        if so:
            body = (body.rstrip() + "\n\n" + so).strip()
        body = _format_body_paragraphs(body)
        return subj, _truncate_to_word_limit(body, max_words)
