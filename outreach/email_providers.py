"""Multiple email finder APIs with fallback when one hits quota or returns nothing."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Callable

import httpx

from outreach.models import LeadRow

SLEEP_BETWEEN_CALLS_SEC = 0.55

# Snov OAuth token cache (process lifetime)
_snov_token: dict[str, float | str] = {"access_token": "", "expires_at": 0.0}


@dataclass(frozen=True)
class LookupOutcome:
    """email set => success. try_next => caller should try the next provider in the chain."""

    email: str | None
    source: str
    try_next: bool = False


def _sleep() -> None:
    time.sleep(SLEEP_BETWEEN_CALLS_SEC)


def hunter_lookup(domain: str, api_key: str) -> LookupOutcome:
    url = "https://api.hunter.io/v2/domain-search"
    params = {"domain": domain, "api_key": api_key, "limit": 5}
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url, params=params)
    if r.status_code == 401:
        return LookupOutcome(None, "hunter_auth_error", try_next=True)
    if r.status_code in (402, 403, 429):
        return LookupOutcome(None, f"hunter_http_{r.status_code}_quota_or_rate", try_next=True)
    if r.status_code >= 500:
        return LookupOutcome(None, f"hunter_http_{r.status_code}", try_next=True)
    if not r.is_success:
        return LookupOutcome(None, f"hunter_http_{r.status_code}", try_next=True)
    data = r.json()
    emails = (data.get("data") or {}).get("emails") or []
    if not emails:
        return LookupOutcome(None, "hunter_not_found", try_next=True)
    best: tuple[float, str] | None = None
    for e in emails:
        conf = float(e.get("confidence") or 0)
        val = (e.get("value") or "").strip()
        if not val or "@" not in val:
            continue
        if best is None or conf > best[0]:
            best = (conf, val)
    if best:
        return LookupOutcome(best[1], "hunter_domain_search", try_next=False)
    return LookupOutcome(None, "hunter_not_found", try_next=True)


def _snov_refresh_token(client_id: str, client_secret: str, client: httpx.Client) -> str | None:
    global _snov_token
    now = time.time()
    if _snov_token["access_token"] and now < float(_snov_token["expires_at"]) - 60:
        return str(_snov_token["access_token"])
    r = client.post(
        "https://api.snov.io/v1/oauth/access_token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    if not r.is_success:
        return None
    try:
        data = r.json()
    except json.JSONDecodeError:
        return None
    token = (data.get("access_token") or data.get("token") or "").strip()
    if not token:
        return None
    expires_in = float(data.get("expires_in") or 3600)
    _snov_token["access_token"] = token
    _snov_token["expires_at"] = now + expires_in
    return token


def snov_lookup(domain: str, client_id: str, client_secret: str) -> LookupOutcome:
    with httpx.Client(timeout=45.0) as client:
        token = _snov_refresh_token(client_id, client_secret, client)
        if not token:
            return LookupOutcome(None, "snov_auth_error", try_next=True)
        url = "https://api.snov.io/v2/domain-emails-with-info"
        params = {"domain": domain, "type": "all", "limit": 20}
        r = client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code == 401:
            r = client.get(
                url,
                params={**params, "access_token": token},
            )
    if r.status_code in (401, 403):
        _snov_token["access_token"] = ""
        _snov_token["expires_at"] = 0.0
        return LookupOutcome(None, "snov_auth_error", try_next=True)
    if r.status_code == 429:
        return LookupOutcome(None, "snov_rate_limited", try_next=True)
    if r.status_code in (402, 451):
        return LookupOutcome(None, f"snov_http_{r.status_code}_quota", try_next=True)
    if r.status_code >= 500:
        return LookupOutcome(None, f"snov_http_{r.status_code}", try_next=True)
    if not r.is_success:
        return LookupOutcome(None, f"snov_http_{r.status_code}", try_next=True)
    try:
        data = r.json()
    except json.JSONDecodeError:
        return LookupOutcome(None, "snov_bad_json", try_next=True)

    emails = data.get("emails") or data.get("data") or []
    if isinstance(emails, dict):
        emails = emails.get("emails") or []
    if not emails:
        return LookupOutcome(None, "snov_not_found", try_next=True)

    best: str | None = None
    for item in emails:
        if isinstance(item, str) and "@" in item:
            best = item.strip()
            break
        if isinstance(item, dict):
            em = (item.get("email") or item.get("value") or "").strip()
            if em and "@" in em:
                best = em
                break
    if best:
        return LookupOutcome(best, "snov_domain_emails", try_next=False)
    return LookupOutcome(None, "snov_not_found", try_next=True)


def _extract_email_from_json(obj: object) -> str | None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "email" and isinstance(v, str) and "@" in v:
                return v.strip()
            found = _extract_email_from_json(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _extract_email_from_json(item)
            if found:
                return found
    return None


def apollo_lookup(row: LeadRow, domain: str, api_key: str) -> LookupOutcome:
    """Uses people bulk_match + reveal_personal_emails (consumes Apollo credits when it matches)."""
    detail: dict[str, str] = {"domain": domain}
    if row.company_name:
        detail["organization_name"] = row.company_name
    if row.founder_name:
        parts = row.founder_name.strip().split(None, 1)
        detail["first_name"] = parts[0]
        if len(parts) > 1:
            detail["last_name"] = parts[1]

    url = "https://api.apollo.io/api/v1/people/bulk_match"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }
    payload = {"details": [detail], "reveal_personal_emails": True}

    with httpx.Client(timeout=45.0) as client:
        r = client.post(url, headers=headers, json=payload)

    if r.status_code in (401, 403):
        return LookupOutcome(None, "apollo_auth_error", try_next=True)
    if r.status_code == 429:
        return LookupOutcome(None, "apollo_rate_limited", try_next=True)
    if r.status_code in (402, 422):
        return LookupOutcome(None, f"apollo_http_{r.status_code}_quota_or_validation", try_next=True)
    if r.status_code >= 500:
        return LookupOutcome(None, f"apollo_http_{r.status_code}", try_next=True)
    if not r.is_success:
        return LookupOutcome(None, f"apollo_http_{r.status_code}", try_next=True)

    try:
        data = r.json()
    except json.JSONDecodeError:
        return LookupOutcome(None, "apollo_bad_json", try_next=True)

    email = _extract_email_from_json(data)
    if email:
        return LookupOutcome(email, "apollo_bulk_match", try_next=False)
    return LookupOutcome(None, "apollo_not_found", try_next=True)


ProviderFn = Callable[[LeadRow, str], LookupOutcome]


def build_provider_chain() -> list[tuple[str, ProviderFn]]:
    """Order: Hunter → Snov → Apollo (only providers with keys set)."""

    chain: list[tuple[str, ProviderFn]] = []

    h_key = os.environ.get("HUNTER_API_KEY", "").strip()
    if h_key:

        def _h(row: LeadRow, domain: str) -> LookupOutcome:
            return hunter_lookup(domain, h_key)

        chain.append(("hunter", _h))

    snov_id = os.environ.get("SNOV_CLIENT_ID", "").strip()
    snov_secret = os.environ.get("SNOV_CLIENT_SECRET", "").strip()
    if snov_id and snov_secret:

        def _s(row: LeadRow, domain: str) -> LookupOutcome:
            return snov_lookup(domain, snov_id, snov_secret)

        chain.append(("snov", _s))

    apollo_key = os.environ.get("APOLLO_API_KEY", "").strip()
    if apollo_key:

        def _a(row: LeadRow, domain: str) -> LookupOutcome:
            return apollo_lookup(row, domain, apollo_key)

        chain.append(("apollo", _a))

    return chain


def lookup_email_for_domain(row: LeadRow, domain: str, chain: list[tuple[str, ProviderFn]]) -> tuple[str | None, str]:
    last_source = "no_providers_configured"
    for i, (_name, fn) in enumerate(chain):
        if i:
            _sleep()
        out = fn(row, domain)
        last_source = out.source
        if out.email:
            return out.email, out.source
        if not out.try_next:
            return None, out.source
    return None, last_source
