"""Fetch common public paths on a company site and extract emails from HTML (D)."""

from __future__ import annotations

import os
import time
from urllib.parse import urlparse

import httpx

from outreach.extract import normalize_page_url
from outreach.founder_names import founder_name_pairs, generic_mailbox, score_email_for_founder
from outreach.html_emails import extract_emails_from_html, origin_from_website

# Polite delay between path fetches on the same host.
_SCRAPE_PATH_DELAY = 0.4
_MAX_BYTES = 750_000

_CONTACT_PATHS = (
    "/",
    "/contact",
    "/about",
    "/team",
)

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _paths_enabled() -> bool:
    v = os.environ.get("OUTREACH_SCRAPE_CONTACT_PAGES", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def pick_best_email(emails: list[str], founder_name: str, domain: str) -> str | None:
    """Prefer founder-matching emails; otherwise generic mailboxes; avoid wrong employees."""
    if not emails:
        return None
    dom = domain.lower().lstrip(".")
    on_domain: list[str] = []
    for e in emails:
        d = e.split("@", 1)[-1].lower()
        if d == dom or d.endswith("." + dom):
            on_domain.append(e)
    pool = on_domain or list(emails)
    if not founder_name_pairs(founder_name):
        generic = [e for e in pool if generic_mailbox(e)]
        return (generic or pool)[0]

    ranked = sorted(pool, key=lambda e: score_email_for_founder(e, founder_name, domain), reverse=True)
    best = ranked[0]
    if score_email_for_founder(best, founder_name, domain) >= 100:
        return best
    generic = [e for e in ranked if generic_mailbox(e)]
    if generic:
        return generic[0]
    return None


def collect_emails_for_company_domain(
    company_website: str,
    domain: str,
    cache_by_domain: dict[str, list[str]],
) -> list[str]:
    """GET well-known paths on the site; return unique emails tied to ``domain``."""
    dom = (domain or "").lower().lstrip(".")
    if dom in cache_by_domain:
        return cache_by_domain[dom]
    out_set: set[str] = set()
    if not _paths_enabled():
        cache_by_domain[dom] = []
        return []

    origin = origin_from_website(company_website)
    if not origin:
        cache_by_domain[dom] = []
        return []
    try:
        host = urlparse(origin).netloc.lower()
        site_host = urlparse(normalize_page_url(company_website)).netloc.lower()
        if site_host.rstrip(".") != host.rstrip("."):
            cache_by_domain[dom] = []
            return []
    except Exception:
        cache_by_domain[dom] = []
        return []

    allowed = frozenset({dom})
    base = origin.rstrip("/")

    with httpx.Client(follow_redirects=True, timeout=22.0) as client:
        for i, path in enumerate(_CONTACT_PATHS):
            if i:
                time.sleep(_SCRAPE_PATH_DELAY)
            url = base + path
            try:
                r = client.get(url, headers=_DEFAULT_HEADERS)
                if r.status_code >= 400:
                    continue
                if len(r.content) > _MAX_BYTES:
                    continue
                ctype = (r.headers.get("content-type") or "").lower()
                if "html" not in ctype and "<html" not in (r.text or "")[:2000].lower():
                    continue
                for em in extract_emails_from_html(r.text or "", allowed_domain_suffixes=allowed):
                    out_set.add(em)
            except (httpx.RequestError, httpx.HTTPStatusError, OSError, ValueError):
                continue

    result = sorted(out_set)
    cache_by_domain[dom] = result
    return result
