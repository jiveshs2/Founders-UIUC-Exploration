from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from outreach.browser_fetch import fetch_rendered_html, url_likely_needs_browser
from outreach.env_loader import groq_key_missing_message, load_environment
from outreach.models import ExtractResult, LeadRow

# Full page fetch cap (local); Groq sees a smaller slice below.
MAX_CHARS = 120_000
# On-demand tier is often ~12k TPM per request; large pages + huge max_tokens exceed that.
_DEFAULT_GROQ_PAGE = 10_000
_DEFAULT_GROQ_MAX_OUT = 4096


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
    def _text_with_links(soup: BeautifulSoup) -> str:
        # Preserve external URLs from anchor tags so company websites are visible
        # to the extractor model (important for directory pages like YC).
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            label = a.get_text(" ", strip=True)
            if href.startswith("//"):
                href = "https:" + href
            if href.startswith(("http://", "https://")):
                a.replace_with(f"{label} ({href})" if label else href)
        return soup.get_text(separator="\n", strip=True)

    try:
        from readability import Document

        doc = Document(html)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "lxml")
        return _text_with_links(soup)
    except Exception:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return _text_with_links(soup)


_STATIC_TEXT_TOO_SHORT = 2_500


def fetch_page_text_and_html(url: str) -> tuple[str, str]:
    """Download once; return (plain text for Groq, raw HTML for mailto/JSON-LD parsing)."""
    url = normalize_page_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    html_used = ""
    try:
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            html_used = r.text or ""
            text = _main_text(html_used)
            if len(text.strip()) < _STATIC_TEXT_TOO_SHORT and url_likely_needs_browser(url):
                try:
                    html = fetch_rendered_html(url)
                    html_used = html
                    text2 = _main_text(html)
                    if len(text2.strip()) < 800:
                        soup = BeautifulSoup(html, "lxml")
                        for tag in soup(["script", "style", "noscript"]):
                            tag.decompose()
                        text2 = soup.get_text(separator="\n", strip=True)
                    if len(text2.strip()) > len(text.strip()):
                        text = text2
                except ImportError as e:
                    raise ValueError(str(e)) from e
                except Exception as e:
                    raise ValueError(
                        f"Browser rendering failed for this URL ({e}). "
                        "Run `playwright install chromium` after `pip install playwright`, then retry."
                    ) from e
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response else "?"
        raise ValueError(
            f"The website returned error {code}. The link may be wrong or the site blocks downloads."
        ) from e
    except httpx.RequestError as e:
        raise ValueError(
            f"Could not reach the website ({e}). Check your internet connection and that the URL is correct."
        ) from e
    except UnicodeError as e:
        raise ValueError(
            f"Invalid hostname in URL {url!r}. Use a real domain (paste the full address from your browser)."
        ) from e
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[truncated]"
    return text, html_used


def fetch_page_text(url: str) -> str:
    return fetch_page_text_and_html(url)[0]


def _is_yc_company_detail_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    host = (p.hostname or "").lower()
    path = (p.path or "").strip("/")
    return "ycombinator.com" in host and path.startswith("companies/") and path.count("/") == 1


def _looks_like_person_name(line: str) -> bool:
    s = re.sub(r"\s+", " ", (line or "").strip())
    if not s or len(s) > 60:
        return False
    if any(ch.isdigit() for ch in s):
        return False
    words = [w for w in s.split() if w]
    if not (2 <= len(words) <= 4):
        return False
    banned = {
        "founder",
        "company",
        "jobs",
        "active",
        "batch",
        "status",
        "team",
        "launches",
        "partner",
    }
    if any(w.lower() in banned for w in words):
        return False
    return all(re.match(r"^[A-Z][A-Za-z.'\-]*$", w) for w in words)


def extract_yc_company_detail(page_html: str, source_url: str) -> ExtractResult | None:
    """Parse a YC single-company page directly to avoid LLM confusion with launch-post content."""
    if not _is_yc_company_detail_url(source_url):
        return None
    soup = BeautifulSoup(page_html or "", "lxml")
    title = (soup.title.get_text(" ", strip=True) if soup.title else "").strip()
    company_name = title.split(":", 1)[0].strip() if ":" in title else ""
    if not company_name:
        h1 = soup.find(["h1", "h2"])
        if h1:
            company_name = h1.get_text(" ", strip=True)
    company_name = company_name.replace("Home›Companies›", "").strip()
    if not company_name:
        return ExtractResult(rows=[], raw_model_text="[yc_parser] could not determine company name")

    website = _recover_company_website_from_html(company_name, page_html, source_url)

    text_lines = [ln.strip() for ln in soup.get_text("\n", strip=True).splitlines()]
    lines = [ln for ln in text_lines if ln]
    founders: list[str] = []
    if "Active Founders" in lines:
        start = lines.index("Active Founders") + 1
        stop = len(lines)
        for marker in ("Company Launches", "Jobs at", "Jobs", "Footer"):
            if marker in lines[start:]:
                stop = start + lines[start:].index(marker)
                break
        seen: set[str] = set()
        for ln in lines[start:stop]:
            if not _looks_like_person_name(ln):
                continue
            low = ln.lower()
            if low in seen:
                continue
            seen.add(low)
            founders.append(ln)
    founder_name = " & ".join(founders[:3])

    industry = ""
    raw_text = "\n".join(lines[:200])
    m = re.search(rf"{re.escape(company_name)}\n(.{{0,120}}?)\nY Combinator Logo", raw_text, flags=re.S)
    if m:
        industry = re.sub(r"\s+", " ", m.group(1)).strip()

    row = LeadRow(
        company_name=company_name,
        founder_name=founder_name,
        industry=industry,
        company_website=website,
        notes="",
    )
    return ExtractResult(rows=[row], raw_model_text="[yc_parser] parsed company detail page")


def _strip_markdown_fences(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _coerce_to_object_list(data: object) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("rows", "companies", "data", "items", "results", "startups"):
            v = data.get(key)
            if isinstance(v, list):
                out = [x for x in v if isinstance(x, dict)]
                if out:
                    return out
    raise ValueError("Expected a JSON array or an object containing a rows/companies/data array")


def _parse_json_array(raw: str) -> list[dict]:
    raw = _strip_markdown_fences(raw)
    m = re.search(r"\[[\s\S]*\]|\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    data = json.loads(raw)
    return _coerce_to_object_list(data)


def _get_field(item: dict, *keys: str) -> str:
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return str(item[k]).strip()
    lower_map = {str(x).lower().replace(" ", "_").replace("-", "_"): v for x, v in item.items()}
    for k in keys:
        kk = k.lower()
        if kk in lower_map and lower_map[kk] not in (None, ""):
            return str(lower_map[kk]).strip()
    return ""


def _first_url_in_text(value: str) -> str:
    if not value:
        return ""
    m = re.search(r"https?://[^\s)\]\"'>]+", value, flags=re.I)
    return m.group(0).strip() if m else ""


def _website_from_item(item: dict) -> str:
    direct = _get_field(item, "company_website", "website", "url", "domain", "homepage", "Company Website")
    if direct:
        if direct.startswith("http://") or direct.startswith("https://") or direct.startswith("//"):
            return direct
        # Sometimes model may return domain only.
        if "." in direct and " " not in direct:
            return f"https://{direct}"
    # Fallback: look for first URL in common textual fields.
    for k in ("notes", "description", "summary", "company_name", "name"):
        v = _get_field(item, k)
        u = _first_url_in_text(v)
        if u:
            return u
    return ""


def _normalized_company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _host_key(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return re.sub(r"[^a-z0-9]+", "", host.split(".", 1)[0])


def _looks_like_company_site(url: str, source_host: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if host.startswith("www."):
        host = host[4:]
    blocked = (
        source_host,
        "ycombinator.com",
        "linkedin.com",
        "x.com",
        "twitter.com",
        "facebook.com",
        "instagram.com",
        "github.com",
        "youtube.com",
        "crunchbase.com",
        "angel.co",
        "wellfound.com",
        "medium.com",
    )
    return not any(host == b or host.endswith("." + b) for b in blocked if b)


def recover_company_website_from_page_text(company_name: str, page_text: str, source_url: str) -> str:
    """Best-effort recovery of the exact company website from nearby URLs in source text."""
    name = (company_name or "").strip()
    text = page_text or ""
    if not name or not text:
        return ""
    try:
        source_host = (urlparse(source_url).hostname or "").lower()
    except Exception:
        source_host = ""

    pattern = re.compile(re.escape(name), flags=re.I)
    urls_re = re.compile(r"https?://[^\s)\]\"'>]+", flags=re.I)
    company_key = _normalized_company_key(name)
    best_url = ""
    best_score = -10_000

    for match in pattern.finditer(text):
        start = max(0, match.start() - 200)
        end = min(len(text), match.end() + 900)
        window = text[start:end]
        for url_match in urls_re.finditer(window):
            url = url_match.group(0).strip().rstrip(".,;:")
            if not _looks_like_company_site(url, source_host):
                continue
            host_key = _host_key(url)
            if not host_key:
                continue
            score = 0
            if company_key and host_key == company_key:
                score += 200
            elif company_key and (host_key in company_key or company_key in host_key):
                score += 120
            distance = abs((start + url_match.start()) - match.start())
            score -= min(distance, 800) // 20
            if score > best_score:
                best_score = score
                best_url = url
    return best_url if best_score >= 80 else ""


def _recover_company_website_from_html(company_name: str, page_html: str, source_url: str) -> str:
    name = (company_name or "").strip()
    html = page_html or ""
    if not name or not html:
        return ""
    try:
        source_host = (urlparse(source_url).hostname or "").lower()
    except Exception:
        source_host = ""

    soup = BeautifulSoup(html, "lxml")
    company_key = _normalized_company_key(name)
    best_url = ""
    best_score = -10_000
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href.startswith(("http://", "https://")):
            continue
        if not _looks_like_company_site(href, source_host):
            continue
        host_key = _host_key(href)
        if not host_key:
            continue
        text = a.get_text(" ", strip=True)
        score = 0
        if company_key and host_key == company_key:
            score += 220
        elif company_key and (host_key in company_key or company_key in host_key):
            score += 150
        if href.rstrip("/").lower() == text.rstrip("/").lower():
            score += 60
        if score > best_score:
            best_score = score
            best_url = href
    return best_url if best_score >= 120 else ""


def recover_company_websites(
    rows: list[LeadRow], page_text: str, source_url: str, page_html: str = ""
) -> list[LeadRow]:
    """Fill blank company_website fields from source-page content before domain guessing."""
    out: list[LeadRow] = []
    for row in rows:
        if row.company_website:
            out.append(row)
            continue
        recovered = _recover_company_website_from_html(row.company_name, page_html, source_url)
        if not recovered:
            recovered = recover_company_website_from_page_text(row.company_name, page_text, source_url)
        if recovered:
            row = row.model_copy(update={"company_website": recovered})
        out.append(row)
    return out


def _row_has_content(base: dict) -> bool:
    return bool(
        str(base.get("company_name", "")).strip()
        or str(base.get("founder_name", "")).strip()
        or str(base.get("company_website", "")).strip()
    )


def _groq_page_cap() -> int:
    raw = os.environ.get("GROQ_MAX_PAGE_CHARS", "").strip()
    if raw.isdigit():
        return max(2_000, min(int(raw), MAX_CHARS))
    return _DEFAULT_GROQ_PAGE


def _groq_max_output_tokens() -> int:
    raw = os.environ.get("GROQ_EXTRACT_MAX_TOKENS", "").strip()
    if raw.isdigit():
        return max(512, min(int(raw), 8192))
    return _DEFAULT_GROQ_MAX_OUT


def _clip_prompt(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[extract instructions truncated to {limit} chars]"


def extract_rows_with_groq(
    page_text: str,
    extract_prompt: str,
    source_url: str,
    model: str | None = None,
) -> ExtractResult:
    from groq import APIStatusError, Groq

    load_environment()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(groq_key_missing_message())
    model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    system = """You extract company rows from the page for a fixed spreadsheet schema. Output ONLY valid JSON: a JSON array, or an object with a "rows" array.

Each object MUST use exactly these string keys (you know this schema; the user does not name columns):
- company_name
- founder_name  ← CRITICAL: capture every founder/CEO name shown. On YC and similar directories, founder names are listed next to each company — never leave this blank if a name is visible. If multiple founders, join with " & " or ", ".
- industry
- company_website (full https URL if on the page, else "")
- email_contact (only if an email for that company appears on the page, else "")
- notes (optional one short line of extra context, else "")

Use "" for unknown fields. The user message only says which companies to include — not which fields to export.

If the page lists companies, include one object per company that matches their filter. Prefer partial data over skipping a row. Only output [] if there are no matching companies or no listings in the text.

No markdown fences. No commentary outside the JSON."""

    max_out = _groq_max_output_tokens()
    clip_prompt = _clip_prompt(extract_prompt, 4_000)
    client = Groq(api_key=api_key)

    caps = [_groq_page_cap(), _groq_page_cap() // 2, _groq_page_cap() // 4, 6_000, 3_000]
    caps = sorted({c for c in caps if c >= 2_000}, reverse=True)

    last_err: str | None = None
    raw_text = ""

    for cap in caps:
        body = page_text[:cap]
        if len(page_text) > cap:
            body += (
                "\n\n[Page text truncated for Groq token limits. "
                "For best results use a URL that lists only the batch/section you need, "
                "or narrow the inclusion filter.]"
            )
        user = f"""Source page URL: {source_url}

{clip_prompt}

Page text:
---
{body}
---
"""

        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=max_out,
            )
            ch0 = completion.choices[0] if completion.choices else None
            raw_text = (ch0.message.content if ch0 and ch0.message else "") or ""
            break
        except APIStatusError as e:
            code = getattr(e, "status_code", None)
            msg = str(e)
            last_err = msg
            too_big = code == 413 or "too large" in msg.lower() or "token" in msg.lower()
            rate = code == 429 or "rate" in msg.lower()
            if too_big or rate:
                time.sleep(1.0)
                continue
            raise
        except Exception as e:
            msg = str(e).lower()
            if "413" in msg or "too large" in msg or "token" in msg or "429" in msg or "rate" in msg:
                last_err = str(e)
                continue
            raise

    if not raw_text and last_err:
        raise RuntimeError(f"[Groq error after trying smaller inputs] {last_err}")
    try:
        items = _parse_json_array(raw_text)
    except (json.JSONDecodeError, ValueError) as e:
        return ExtractResult(rows=[], raw_model_text=raw_text + f"\n\n[parse error: {e}]")

    rows: list[LeadRow] = []
    for item in items:
        ec = _get_field(item, "email_contact", "email", "Email") or ""
        email_val = ec if ec and "@" in ec else None
        base = {
            "company_name": _get_field(item, "company_name", "company", "Company Name", "name"),
            "founder_name": _get_field(
                item, "founder_name", "founder", "Founder", "founders", "ceo", "CEO"
            ),
            "industry": _get_field(item, "industry", "batch", "sector", "vertical"),
            "company_website": _website_from_item(item),
            "notes": _get_field(item, "notes", "description", "summary"),
            "email": email_val,
        }
        if not _row_has_content(base):
            continue
        try:
            rows.append(LeadRow.model_validate(base))
        except Exception:
            rows.append(LeadRow(**base))
    return ExtractResult(rows=rows, raw_model_text=raw_text)


def extract_rows_with_gemini(
    page_text: str,
    extract_prompt: str,
    source_url: str,
    model: str | None = None,
) -> ExtractResult:
    """Gemini alternative to Groq for structured row extraction."""
    load_environment()

    system = """You extract company rows from the page for a fixed spreadsheet schema. Output ONLY valid JSON: a JSON array, or an object with a "rows" array.

Each object MUST use exactly these string keys (you know this schema; the user does not name columns):
- company_name
- founder_name  ← CRITICAL: capture every founder/CEO name shown. On YC and similar directories, founder names are listed next to each company — never leave this blank if a name is visible. If multiple founders, join with " & " or ", ".
- industry
- company_website (full https URL if on the page, else "")
- email_contact (only if an email for that company appears on the page, else "")
- notes (optional one short line of extra context, else "")

Use "" for unknown fields. The user message only says which companies to include — not which fields to export.

If the page lists companies, include one object per company that matches their filter. Prefer partial data over skipping a row. Only output [] if there are no matching companies or no listings in the text.

No markdown fences. No commentary outside the JSON."""

    clip_prompt = _clip_prompt(extract_prompt, 4_000)
    caps = [_groq_page_cap(), _groq_page_cap() // 2, _groq_page_cap() // 4, 6_000, 3_000]
    caps = sorted({c for c in caps if c >= 2_000}, reverse=True)

    from outreach.gemini_api import gemini_generate_text

    last_err: str | None = None
    raw_text = ""
    for cap in caps:
        body = page_text[:cap]
        if len(page_text) > cap:
            body += (
                "\n\n[Page text truncated for token limits. "
                "For best results use a URL that lists only the batch/section you need, "
                "or narrow the inclusion filter.]"
            )
        user = f"""Source page URL: {source_url}

{clip_prompt}

Page text:
---
{body}
---
"""
        try:
            res = gemini_generate_text(
                system=system,
                user=user,
                model=model,
                temperature=0.2,
                max_output_tokens=_groq_max_output_tokens(),
                timeout_sec=75.0,
            )
            raw_text = res.text or ""
            break
        except Exception as e:
            last_err = str(e)
            continue

    if not raw_text and last_err:
        return ExtractResult(rows=[], raw_model_text=f"[Gemini error] {last_err}")

    try:
        items = _parse_json_array(raw_text)
    except (json.JSONDecodeError, ValueError) as e:
        return ExtractResult(rows=[], raw_model_text=raw_text + f"\n\n[parse error: {e}]")

    rows: list[LeadRow] = []
    for item in items:
        ec = _get_field(item, "email_contact", "email", "Email") or ""
        email_val = ec if ec and "@" in ec else None
        base = {
            "company_name": _get_field(item, "company_name", "company", "Company Name", "name"),
            "founder_name": _get_field(item, "founder_name", "founder", "Founder", "founders", "ceo", "CEO"),
            "industry": _get_field(item, "industry", "batch", "sector", "vertical"),
            "company_website": _website_from_item(item),
            "notes": _get_field(item, "notes", "description", "summary"),
            "email": email_val,
        }
        if not _row_has_content(base):
            continue
        try:
            rows.append(LeadRow.model_validate(base))
        except Exception:
            rows.append(LeadRow(**base))
    return ExtractResult(rows=rows, raw_model_text=raw_text)
