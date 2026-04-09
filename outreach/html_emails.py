"""Extract email addresses from raw HTML (mailto:, JSON-LD, visible text)."""

from __future__ import annotations

import json
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9][a-zA-Z0-9._%+\-]*@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.I,
)


def _normalize_candidate(s: str) -> str | None:
    s = (s or "").strip().strip("<>").strip()
    if not s or "@" not in s:
        return None
    if "?" in s:
        s = s.split("?", 1)[0]
    m = _EMAIL_RE.search(s.replace(" ", ""))
    if not m:
        return None
    return m.group(0).lower()


def extract_emails_from_html(
    html: str,
    *,
    allowed_domain_suffixes: frozenset[str] | None = None,
) -> list[str]:
    """
    Pull emails from mailto links, application/ld+json blocks, and decoded text.
    When ``allowed_domain_suffixes`` is set, only addresses whose domain equals or
    ends with one of those suffixes are kept (e.g. company domain).
    """
    if not html or not html.strip():
        return []
    found: set[str] = set()
    soup = BeautifulSoup(html, "lxml")

    for a in soup.find_all("a", href=True):
        h = (a.get("href") or "").strip()
        if h.lower().startswith("mailto:"):
            body = unquote(h[7:])
            em = _normalize_candidate(body)
            if em:
                found.add(em)

    for script in soup.find_all("script", attrs={"type": True}):
        t = (script.get("type") or "").lower()
        if "ld+json" not in t:
            continue
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack: list = [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                for k, v in obj.items():
                    lk = str(k).lower()
                    if lk in ("email", "e-mail") and isinstance(v, str):
                        em = _normalize_candidate(v)
                        if em:
                            found.add(em)
                    elif isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(obj, list):
                stack.extend(obj)

    text_blob = soup.get_text(" ", strip=False)
    text_blob = text_blob + " " + html
    text_blob = re.sub(r"\s*\[at\]\s*", "@", text_blob, flags=re.I)
    text_blob = re.sub(r"\s*\(at\)\s*", "@", text_blob, flags=re.I)
    text_blob = re.sub(r"\s*\[dot\]\s*", ".", text_blob, flags=re.I)
    for m in _EMAIL_RE.finditer(text_blob):
        em = _normalize_candidate(m.group(0))
        if em:
            found.add(em)

    out = sorted(found)
    if not allowed_domain_suffixes:
        return out
    suffixes = {s.lower().lstrip(".") for s in allowed_domain_suffixes}
    suffixes.discard("")

    def allowed(email: str) -> bool:
        dom = email.split("@", 1)[-1].lower()
        return any(dom == s or dom.endswith("." + s) for s in suffixes)

    return [e for e in out if allowed(e)]


def origin_from_website(company_website: str) -> str | None:
    """https://example.com/foo → https://example.com"""
    from outreach.extract import normalize_page_url

    if not (company_website or "").strip():
        return None
    u = normalize_page_url(company_website.strip())
    from urllib.parse import urlparse

    p = urlparse(u)
    if not p.scheme or not p.netloc:
        return None
    return f"{p.scheme}://{p.netloc}"
