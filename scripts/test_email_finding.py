"""Exercise the email-finding pipeline end-to-end against a real public site.

Run from the project root:
    .venv/bin/python scripts/test_email_finding.py
"""

from __future__ import annotations

import sys

from outreach.contact_scrape import collect_emails_for_company_domain, pick_best_email
from outreach.enrich import enrich_rows_email
from outreach.env_loader import load_environment
from outreach.models import LeadRow
from outreach.pattern_verify import try_pattern_verified_email


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def test_contact_scrape() -> None:
    """Discover emails from a site we know exposes them on its contact page."""
    banner("TEST 1: contact-page scrape (python.org expose 'webmaster@python.org')")
    cache: dict[str, list[str]] = {}
    found = collect_emails_for_company_domain("https://www.python.org", "python.org", cache)
    print(f"Found {len(found)} email(s) on python.org: {found[:5]}")
    if found:
        print("PASS: scraper extracted at least one address.")
    else:
        print("FAIL: scraper returned nothing.")


def test_pattern_unverified() -> None:
    """When no verifier key is set, we should still get a single best-guess."""
    banner("TEST 2: unverified pattern fallback")
    em, src = try_pattern_verified_email("Sam", "Altman", "openai.com", founder_raw="Sam Altman")
    print(f"Guess for Sam Altman @ openai.com: {em} (source: {src})")
    if em:
        print("PASS: got a fallback guess.")
    else:
        print("FAIL: no guess produced.")


def test_full_enrich() -> None:
    """End-to-end: a row with a known website + founder name."""
    banner("TEST 3: full enrich on a known YC company (Coasts)")
    rows = [
        LeadRow(
            company_name="Coasts",
            founder_name="Cindy Quach",
            company_website="https://coasts.dev",
            industry="B2B",
        )
    ]
    cache: dict = {}
    out = enrich_rows_email(rows, cache=cache)
    for r in out:
        print(f"  {r.company_name} -> {r.email or '(none)'} [{r.email_source or 'unknown'}]")


def test_pick_best() -> None:
    banner("TEST 4: pick_best_email selection logic")
    pool = [
        "info@example.com",
        "alice.smith@example.com",
        "bob@example.com",
        "marketing@otherdomain.com",
    ]
    best = pick_best_email(pool, "Alice Smith", "example.com")
    print(f"With founder Alice Smith: {best} (expected alice.smith@example.com)")
    best2 = pick_best_email(pool, "", "example.com")
    print(f"With no founder: {best2} (expected info@example.com)")


def main() -> int:
    load_environment()
    try:
        test_contact_scrape()
    except Exception as e:
        print(f"FAIL: contact_scrape raised: {e}")
    try:
        test_pattern_unverified()
    except Exception as e:
        print(f"FAIL: pattern_unverified raised: {e}")
    try:
        test_pick_best()
    except Exception as e:
        print(f"FAIL: pick_best raised: {e}")
    try:
        test_full_enrich()
    except Exception as e:
        print(f"FAIL: full_enrich raised: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
