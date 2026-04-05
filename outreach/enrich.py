from __future__ import annotations

from outreach.email_providers import build_provider_chain, lookup_email_for_domain
from outreach.env_loader import load_environment
from outreach.models import LeadRow


def _domain_from_row(row: LeadRow) -> str | None:
    d = row.domain()
    if d:
        return d
    return None


def enrich_rows_hunter(rows: list[LeadRow], cache: dict[str, tuple[str | None, str | None]] | None = None) -> list[LeadRow]:
    """
    Find emails using a chain of providers (Hunter → Snov → Apollo).
    Configure any subset via env; each step runs if the previous returned nothing or hit quota/rate limits.
    """
    load_environment()
    chain = build_provider_chain()
    cache = cache or {}
    out: list[LeadRow] = []

    if not chain:
        for r in rows:
            if not r.email:
                r.email_source = "skipped_no_email_provider_keys"
            out.append(r)
        return out

    for row in rows:
        if row.email:
            row.email_source = row.email_source or "provided"
            out.append(row)
            continue
        domain = _domain_from_row(row)
        if not domain:
            row.email_source = "no_domain"
            out.append(row)
            continue
        if domain in cache:
            email, src = cache[domain]
            row.email = email
            row.email_source = src
            out.append(row)
            continue

        email, src = lookup_email_for_domain(row, domain, chain)
        cache[domain] = (email, src)
        row.email = email
        row.email_source = src
        out.append(row)
    return out
