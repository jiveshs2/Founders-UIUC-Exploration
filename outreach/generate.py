from __future__ import annotations

import json
import os
import re

from outreach.env_loader import groq_key_missing_message, load_environment
from outreach.models import LeadRow


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
) -> tuple[str, str]:
    from groq import Groq

    load_environment()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(groq_key_missing_message())
    model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    ctx = {
        "founder_name": row.founder_name,
        "company_name": row.company_name,
        "batch": row.batch,
        "company_website": row.company_website,
        "email": row.email or "",
        "notes": row.notes,
    }

    system = """You write concise, professional cold outreach emails.
Output ONLY a JSON object with keys "subject" and "body" (plain text, no HTML).
Do not use markdown fences."""

    user = f"""Purpose / intent for this email:
{purpose_prompt}

Lead context (JSON):
{json.dumps(ctx, ensure_ascii=False)}

Write one email addressed appropriately. If email address is missing, still write the body with a generic greeting using the founder or company name if known."""

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
    raw_text = completion.choices[0].message.content or ""
    try:
        return _parse_outreach_json(raw_text)
    except (json.JSONDecodeError, ValueError):
        return "Follow-up", raw_text.strip() or "(empty model response)"
