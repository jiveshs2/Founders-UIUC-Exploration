"""Fetch company-site pages and extract emails (D).

Strategy:
1. Fetch the homepage and pull any emails it exposes (mailto, JSON-LD, text).
2. Discover real "Contact / Team / About / People" links from the homepage and
   follow them (capped). This handles sites that use non-standard paths like
   "/get-in-touch", "/who-we-are", "/leadership".
3. As a backstop, also try a small fixed list of common paths.
4. Optionally render the homepage with a headless browser if static fetches
   yielded zero emails (controlled by ``OUTREACH_RENDER_COMPANY_SITE``).
"""

from __future__ import annotations

import os
import re
import time
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from outreach.extract import normalize_page_url
from outreach.founder_names import founder_name_pairs, generic_mailbox, score_email_for_founder
from outreach.html_emails import extract_emails_from_html, origin_from_website

_SCRAPE_PATH_DELAY = 0.35
_MAX_BYTES = 750_000
_MAX_DISCOVERED_PAGES = 6

_CONTACT_PATHS = (
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/team",
    "/people",
)

_LINK_KEYWORDS = (
    "contact",
    "get in touch",
    "get-in-touch",
    "reach us",
    "reach-us",
    "team",
    "people",
    "about",
    "company",
    "leadership",
    "founders",
    "press",
    "support",
    "help",
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


def _render_company_site_enabled() -> bool:
    v = os.environ.get("OUTREACH_RENDER_COMPANY_SITE", "1").strip().lower()
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


def _link_looks_relevant(text: str, href: str) -> bool:
    blob = (text + " " + href).lower()
    return any(kw in blob for kw in _LINK_KEYWORDS)


def _discover_internal_links(html: str, base_url: str, domain: str) -> list[str]:
    """Find on-site links that look like contact / team / about pages."""
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    dom = domain.lower().lstrip(".")
    seen: set[str] = set()
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        raw_href = (a.get("href") or "").strip()
        if not raw_href or raw_href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        text = a.get_text(" ", strip=True) or ""
        if not _link_looks_relevant(text, raw_href):
            continue
        try:
            absolute = urljoin(base_url, raw_href)
            absolute, _ = urldefrag(absolute)
        except Exception:
            continue
        if not absolute.lower().startswith(("http://", "https://")):
            continue
        host = (urlparse(absolute).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if not (host == dom or host.endswith("." + dom)):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
        if len(out) >= _MAX_DISCOVERED_PAGES:
            break
    return out


def _fetch_html(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url, headers=_DEFAULT_HEADERS)
    except (httpx.RequestError, httpx.HTTPStatusError, OSError, ValueError):
        return None
    if r.status_code >= 400:
        return None
    if len(r.content) > _MAX_BYTES:
        return None
    ctype = (r.headers.get("content-type") or "").lower()
    body = r.text or ""
    if "html" not in ctype and "<html" not in body[:2000].lower():
        return None
    return body


def _emails_from_rendered_homepage(url: str, domain: str) -> set[str]:
    """Last-resort: render the homepage with a headless browser."""
    try:
        from outreach.browser_fetch import fetch_rendered_html
    except Exception:
        return set()
    try:
        html = fetch_rendered_html(url, timeout_ms=45_000)
    except Exception:
        return set()
    if not html:
        return set()
    allowed = frozenset({domain.lower().lstrip(".")})
    return set(extract_emails_from_html(html, allowed_domain_suffixes=allowed))


def collect_emails_for_company_domain(
    company_website: str,
    domain: str,
    cache_by_domain: dict[str, list[str]],
) -> list[str]:
    """GET well-known paths on the site; return unique emails tied to ``domain``."""
    dom = (domain or "").lower().lstrip(".")
    if dom in cache_by_domain:
        return cache_by_domain[dom]
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
    out_set: set[str] = set()
    visited: set[str] = set()

    with httpx.Client(follow_redirects=True, timeout=22.0) as client:
        # 1. Homepage first
        home_url = base + "/"
        visited.add(home_url)
        home_html = _fetch_html(client, home_url)
        if home_html:
            for em in extract_emails_from_html(home_html, allowed_domain_suffixes=allowed):
                out_set.add(em)
            # 2. Discover real contact/team links from homepage
            discovered = _discover_internal_links(home_html, home_url, dom)
            for url in discovered:
                if url in visited:
                    continue
                visited.add(url)
                time.sleep(_SCRAPE_PATH_DELAY)
                html = _fetch_html(client, url)
                if not html:
                    continue
                for em in extract_emails_from_html(html, allowed_domain_suffixes=allowed):
                    out_set.add(em)

        # 3. Fixed-path backstop for paths the homepage didn't link
        for path in _CONTACT_PATHS:
            url = base + path
            if url in visited:
                continue
            visited.add(url)
            time.sleep(_SCRAPE_PATH_DELAY)
            html = _fetch_html(client, url)
            if not html:
                continue
            for em in extract_emails_from_html(html, allowed_domain_suffixes=allowed):
                out_set.add(em)
            if out_set:
                # Got something — no need to probe more random paths.
                break

    # 4. Optional browser render as last resort
    if not out_set and _render_company_site_enabled():
        rendered = _emails_from_rendered_homepage(home_url, dom)
        out_set.update(rendered)

    result = sorted(out_set)
    cache_by_domain[dom] = result
    return result
