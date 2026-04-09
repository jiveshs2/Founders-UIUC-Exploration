from __future__ import annotations

import os

from outreach.contact_scrape import collect_emails_for_company_domain, pick_best_email
from outreach.domain_guess import guess_domains
from outreach.email_providers import build_provider_chain, lookup_email_for_domain
from outreach.env_loader import load_environment
from outreach.founder_names import email_matches_founder
from outreach.models import LeadRow
from outreach.pattern_verify import split_founder_name, try_pattern_verified_email


def _guess_domains_enabled() -> bool:
    v = os.environ.get("OUTREACH_GUESS_DOMAINS", "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _domain_from_row(row: LeadRow) -> str | None:
    d = row.domain()
    if d:
        return d
    return None


def _enrich_cache_key(row: LeadRow) -> tuple[str, str]:
    """Domain + founder identity so the same domain is not reused for a different person."""
    dom = _domain_from_row(row) or ""
    founder = (row.founder_name or "").strip().lower()
    return (dom, founder)


def enrich_rows_email(
    rows: list[LeadRow],
    cache: dict[tuple[str, str], tuple[str | None, str | None]] | None = None,
    scrape_cache: dict[str, list[str]] | None = None,
) -> list[LeadRow]:
    """
    For each row without an email: scrape common site paths (D), run the API
    provider chain, then optional pattern guessing verified by ZeroBounce /
    Abstract (B). Configure providers and verifier keys in ``.env``.
    """
    load_environment()
    chain = build_provider_chain()
    cache = cache or {}
    scrape_cache = scrape_cache or {}
    has_verify_keys = bool(
        os.environ.get("ZEROBOUNCE_API_KEY", "").strip()
        or os.environ.get("ABSTRACT_EMAIL_VALIDATION_API_KEY", "").strip()
    )
    out: list[LeadRow] = []

    for row in rows:
        if row.email:
            row.email_source = row.email_source or "provided"
            out.append(row)
            continue

        domain = _domain_from_row(row)
        domain_was_guessed = False
        guessed_domains: list[str] = []

        if not domain:
            if not _guess_domains_enabled():
                row.email_source = "no_exact_domain"
                out.append(row)
                continue
            guessed_domains = guess_domains((row.company_name or "").strip())
            if guessed_domains:
                domain = guessed_domains[0]
                row.company_website = f"https://{domain}"
                domain_was_guessed = True
            else:
                row.email_source = "no_domain"
                out.append(row)
                continue

        key = _enrich_cache_key(row)
        if key in cache:
            email, src = cache[key]
            row.email = email
            row.email_source = src
            out.append(row)
            continue

        founder = (row.founder_name or "").strip()
        _MAX_GUESSED_DOMAINS = 3
        domains_to_try = [domain]
        if domain_was_guessed and len(guessed_domains) > 1:
            for gd in guessed_domains[1:]:
                if gd != domain:
                    domains_to_try.append(gd)
                if len(domains_to_try) >= _MAX_GUESSED_DOMAINS:
                    break

        email, src = _try_domains_for_email(
            row, domains_to_try, founder, chain, scrape_cache, has_verify_keys,
        )

        if email:
            if src and "guessed_domain:" in (src or ""):
                actual_domain = src.split("guessed_domain:")[-1]
                row.company_website = f"https://{actual_domain}"
                src = src.split("|")[0] if "|" in src else src.replace(f"|guessed_domain:{actual_domain}", "")
            cache[key] = (email, src or "unknown")
            row.email = email
            row.email_source = src or "unknown"
        else:
            fail = src or "no_email_found"
            if not chain and fail == "pattern_verify_no_api_keys" and not has_verify_keys:
                fail = "skipped_no_email_provider_keys"
            row.email_source = fail
            cache[key] = (None, fail)

        out.append(row)

    return out


def _try_single_domain(
    row: LeadRow,
    domain: str,
    founder: str,
    chain: list,
    scrape_cache: dict[str, list[str]],
    *,
    scrape_pages: bool = True,
) -> tuple[str | None, str | None, str | None]:
    """Try scrape → API chain → pattern guess for one domain. Returns (email, source, fail_source)."""
    email: str | None = None
    src: str | None = None
    api_last: str | None = None

    if scrape_pages:
        website = f"https://{domain}"
        found = collect_emails_for_company_domain(website, domain, scrape_cache)
        if found:
            best = pick_best_email(found, founder, domain)
            if best:
                email, src = best, "scrape_company_site"

    if not email and chain:
        website = f"https://{domain}"
        temp_row = row.model_copy(update={"company_website": website})
        email, api_last = lookup_email_for_domain(temp_row, domain, chain)
        if email:
            src = api_last

    pattern_last: str | None = None
    if not email:
        fn, ln = split_founder_name(founder)
        email, pattern_last = try_pattern_verified_email(fn, ln, domain, founder_raw=founder)
        if email:
            src = pattern_last

    return email, src, api_last or pattern_last


def _try_domains_for_email(
    row: LeadRow,
    domains: list[str],
    founder: str,
    chain: list,
    scrape_cache: dict[str, list[str]],
    has_verify_keys: bool,
) -> tuple[str | None, str | None]:
    """Try each domain; prefer one where the email matches the founder name.

    Only the first (primary) domain gets the full contact-page scrape.
    Fallback domains use API chain + pattern guess only (much faster).
    """
    best_email: str | None = None
    best_src: str | None = None
    last_fail: str | None = None

    for i, domain in enumerate(domains):
        email, src, fail_src = _try_single_domain(
            row, domain, founder, chain, scrape_cache,
            scrape_pages=(i == 0),
        )
        if not email:
            last_fail = last_fail or fail_src
            continue
        if founder and email_matches_founder(email, founder):
            return email, src
        if best_email is None:
            best_email, best_src = email, src

    if best_email:
        return best_email, best_src
    return None, last_fail
