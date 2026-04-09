"""Optional browser rendering for JS-heavy sites (e.g. YC company directory)."""

from __future__ import annotations

from urllib.parse import urlparse


def url_likely_needs_browser(url: str) -> bool:
    u = url.lower()
    if "ycombinator.com" in u and "/companies" in u:
        return True
    return False


def fetch_rendered_html(url: str, timeout_ms: int = 90_000) -> str:
    """Return HTML after Chromium executes page JavaScript. Requires: pip install playwright && playwright install chromium"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ImportError(
            "Playwright is not installed. For JavaScript-rendered pages like "
            "https://www.ycombinator.com/companies run:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from e

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    is_yc = "ycombinator.com" in host

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Let client-side lists hydrate (YC directory, etc.)
            page.wait_for_timeout(5_000 if is_yc else 3_000)
            if is_yc:
                for _ in range(4):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1_200)
            return page.content()
        finally:
            browser.close()
