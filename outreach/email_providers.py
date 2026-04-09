"""Email discovery: public-page scrape (see contact_scrape) + provider waterfall.

Configured providers (optional keys in ``.env``) run in order after contact-page
scraping: Hunter → Snov → Apollo → Anymail (company) → Anymail (person) →
Findymail → Skrapp. Pattern guessing + verification runs last in ``enrich`` (see
``pattern_verify``).

Each vendor’s free tier / credits change over time — confirm on their pricing
pages before large runs.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Callable

import httpx

from outreach.contact_scrape import pick_best_email
from outreach.founder_names import email_matches_founder, generic_mailbox, primary_founder_name
from outreach.models import LeadRow
from outreach.pattern_verify import split_founder_name

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


def hunter_lookup(domain: str, api_key: str, founder_name: str = "") -> LookupOutcome:
    url = "https://api.hunter.io/v2/domain-search"
    params = {"domain": domain, "api_key": api_key, "limit": 20}
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
    try:
        data = r.json()
    except json.JSONDecodeError:
        return LookupOutcome(None, "hunter_bad_json", try_next=True)
    if not isinstance(data, dict):
        return LookupOutcome(None, "hunter_bad_json", try_next=True)
    emails_raw = (data.get("data") or {}).get("emails") or []
    if not emails_raw:
        return LookupOutcome(None, "hunter_not_found", try_next=True)
    all_vals: list[str] = []
    for e in emails_raw:
        if not isinstance(e, dict):
            continue
        val = (e.get("value") or "").strip()
        if val and "@" in val:
            all_vals.append(val)
    if not all_vals:
        return LookupOutcome(None, "hunter_not_found", try_next=True)
    best = pick_best_email(all_vals, founder_name, domain)
    if best:
        return LookupOutcome(best, "hunter_domain_search", try_next=False)
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
    try:
        expires_in = float(data.get("expires_in") or 3600)
    except (TypeError, ValueError):
        expires_in = 3600.0
    _snov_token["access_token"] = token
    _snov_token["expires_at"] = now + expires_in
    return token


def snov_lookup(domain: str, client_id: str, client_secret: str, founder_name: str = "") -> LookupOutcome:
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

    emails_raw = data.get("emails") or data.get("data") or []
    if isinstance(emails_raw, dict):
        emails_raw = emails_raw.get("emails") or []
    if not emails_raw:
        return LookupOutcome(None, "snov_not_found", try_next=True)

    all_vals: list[str] = []
    for item in emails_raw:
        if isinstance(item, str) and "@" in item:
            all_vals.append(item.strip())
        elif isinstance(item, dict):
            em = (item.get("email") or item.get("value") or "").strip()
            if em and "@" in em:
                all_vals.append(em)
    if not all_vals:
        return LookupOutcome(None, "snov_not_found", try_next=True)
    best = pick_best_email(all_vals, founder_name, domain)
    if best:
        return LookupOutcome(best, "snov_domain_emails", try_next=False)
    return LookupOutcome(None, "snov_not_found", try_next=True)


def apollo_lookup(row: LeadRow, domain: str, api_key: str) -> LookupOutcome:
    full = primary_founder_name(row.founder_name or "")
    fn, ln = split_founder_name(full)
    if not full and not fn:
        return LookupOutcome(None, "apollo_skip_no_name", try_next=True)
    url = "https://api.apollo.io/api/v1/people/match"
    params: dict[str, str] = {"domain": domain}
    if (row.company_name or "").strip():
        params["organization_name"] = row.company_name.strip()
    if " " in full:
        params["name"] = full
    else:
        params["first_name"] = fn
        if ln:
            params["last_name"] = ln
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    with httpx.Client(timeout=45.0) as client:
        r = client.post(url, params=params, headers=headers)
    if r.status_code in (401, 403):
        return LookupOutcome(None, "apollo_auth_error", try_next=True)
    if r.status_code == 429:
        return LookupOutcome(None, "apollo_rate_limited", try_next=True)
    if r.status_code in (402, 422):
        return LookupOutcome(None, f"apollo_http_{r.status_code}", try_next=True)
    if r.status_code >= 500:
        return LookupOutcome(None, f"apollo_http_{r.status_code}", try_next=True)
    if not r.is_success:
        return LookupOutcome(None, f"apollo_http_{r.status_code}", try_next=True)
    try:
        data = r.json()
    except json.JSONDecodeError:
        return LookupOutcome(None, "apollo_bad_json", try_next=True)
    person = data.get("person") if isinstance(data, dict) else None
    if not isinstance(person, dict):
        return LookupOutcome(None, "apollo_not_found", try_next=True)
    email = (person.get("email") or "").strip()
    if email and "@" in email:
        return LookupOutcome(email, "apollo_people_match", try_next=False)
    return LookupOutcome(None, "apollo_not_found", try_next=True)


def anymail_company_lookup(row: LeadRow, domain: str, api_key: str) -> LookupOutcome:
    url = "https://api.anymailfinder.com/v5.1/find-email/company"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    body: dict[str, str] = {"domain": domain, "email_type": "any"}
    if (row.company_name or "").strip():
        body["company_name"] = row.company_name.strip()
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, headers=headers, json=body)
    if r.status_code == 401:
        return LookupOutcome(None, "anymail_company_auth_error", try_next=True)
    if r.status_code == 402:
        return LookupOutcome(None, "anymail_company_payment_needed", try_next=True)
    if r.status_code == 429:
        return LookupOutcome(None, "anymail_company_rate_limited", try_next=True)
    if r.status_code >= 500:
        return LookupOutcome(None, f"anymail_company_http_{r.status_code}", try_next=True)
    if not r.is_success:
        return LookupOutcome(None, f"anymail_company_http_{r.status_code}", try_next=True)
    try:
        data = r.json()
    except json.JSONDecodeError:
        return LookupOutcome(None, "anymail_company_bad_json", try_next=True)
    raw_list = data.get("valid_emails") or []
    if not isinstance(raw_list, list):
        raw_list = []
    emails = [str(x).strip() for x in raw_list if isinstance(x, str) and "@" in x]
    if not emails:
        return LookupOutcome(None, "anymail_company_not_found", try_next=True)
    best = pick_best_email(emails, row.founder_name or "", domain)
    if best:
        return LookupOutcome(best, "anymail_company", try_next=False)
    return LookupOutcome(None, "anymail_company_not_found", try_next=True)


def anymail_person_lookup(row: LeadRow, domain: str, api_key: str) -> LookupOutcome:
    founder = primary_founder_name(row.founder_name or "")
    fn, ln = split_founder_name(founder)
    if not fn:
        return LookupOutcome(None, "anymail_person_skip_no_name", try_next=True)
    url = "https://api.anymailfinder.com/v5.1/find-email/person"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    body: dict[str, str] = {"domain": domain}
    if ln:
        body["first_name"] = fn
        body["last_name"] = ln
    else:
        body["full_name"] = founder
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, headers=headers, json=body)
    if r.status_code == 401:
        return LookupOutcome(None, "anymail_person_auth_error", try_next=True)
    if r.status_code == 402:
        return LookupOutcome(None, "anymail_person_payment_needed", try_next=True)
    if r.status_code == 429:
        return LookupOutcome(None, "anymail_person_rate_limited", try_next=True)
    if r.status_code >= 500:
        return LookupOutcome(None, f"anymail_person_http_{r.status_code}", try_next=True)
    if not r.is_success:
        return LookupOutcome(None, f"anymail_person_http_{r.status_code}", try_next=True)
    try:
        data = r.json()
    except json.JSONDecodeError:
        return LookupOutcome(None, "anymail_person_bad_json", try_next=True)
    ve = (data.get("valid_email") or "").strip()
    if ve and "@" in ve:
        return LookupOutcome(ve, "anymail_person", try_next=False)
    return LookupOutcome(None, "anymail_person_not_found", try_next=True)


def findymail_lookup(row: LeadRow, domain: str, api_key: str) -> LookupOutcome:
    name = primary_founder_name(row.founder_name or "")
    if not name:
        return LookupOutcome(None, "findymail_skip_no_name", try_next=True)
    url = "https://app.findymail.com/api/search/name"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, headers=headers, json={"name": name, "domain": domain})
    if r.status_code in (401, 403):
        return LookupOutcome(None, "findymail_auth_error", try_next=True)
    if r.status_code == 429:
        return LookupOutcome(None, "findymail_rate_limited", try_next=True)
    if r.status_code in (402, 404):
        return LookupOutcome(None, f"findymail_http_{r.status_code}", try_next=True)
    if r.status_code >= 500:
        return LookupOutcome(None, f"findymail_http_{r.status_code}", try_next=True)
    if not r.is_success:
        return LookupOutcome(None, f"findymail_http_{r.status_code}", try_next=True)
    try:
        data = r.json()
    except json.JSONDecodeError:
        return LookupOutcome(None, "findymail_bad_json", try_next=True)
    if not isinstance(data, dict):
        return LookupOutcome(None, "findymail_not_found", try_next=True)
    for key in ("email", "contact_email"):
        em = data.get(key)
        if isinstance(em, str) and "@" in em:
            return LookupOutcome(em.strip().lower(), "findymail_name", try_next=False)
    contact = data.get("contact")
    if isinstance(contact, dict):
        em = contact.get("email")
        if isinstance(em, str) and "@" in em:
            return LookupOutcome(em.strip().lower(), "findymail_name", try_next=False)
    return LookupOutcome(None, "findymail_not_found", try_next=True)


def skrapp_lookup(row: LeadRow, domain: str, api_key: str) -> LookupOutcome:
    full = primary_founder_name(row.founder_name or "")
    fn, ln = split_founder_name(full)
    url = "https://api.skrapp.io/api/v2/find"
    headers = {"X-Access-Key": api_key, "Content-Type": "application/json"}
    params: dict[str, str] = {"domain": domain}
    if fn and ln:
        params["firstName"] = fn
        params["lastName"] = ln
    elif full:
        params["fullName"] = full
    else:
        return LookupOutcome(None, "skrapp_skip_no_name", try_next=True)
    with httpx.Client(timeout=45.0) as client:
        r = client.get(url, params=params, headers=headers)
    if r.status_code in (401, 403):
        return LookupOutcome(None, "skrapp_auth_error", try_next=True)
    if r.status_code == 429:
        return LookupOutcome(None, "skrapp_rate_limited", try_next=True)
    if r.status_code in (402, 404):
        return LookupOutcome(None, f"skrapp_http_{r.status_code}", try_next=True)
    if r.status_code >= 500:
        return LookupOutcome(None, f"skrapp_http_{r.status_code}", try_next=True)
    if not r.is_success:
        return LookupOutcome(None, f"skrapp_http_{r.status_code}", try_next=True)
    try:
        data = r.json()
    except json.JSONDecodeError:
        return LookupOutcome(None, "skrapp_bad_json", try_next=True)
    if not isinstance(data, dict):
        return LookupOutcome(None, "skrapp_not_found", try_next=True)
    email = (data.get("email") or "").strip()
    if email and "@" in email:
        return LookupOutcome(email.lower(), "skrapp_find", try_next=False)
    return LookupOutcome(None, "skrapp_not_found", try_next=True)


ProviderFn = Callable[[LeadRow, str], LookupOutcome]


def _person_specific_source(source: str) -> bool:
    return source in {
        "apollo_people_match",
        "anymail_person",
        "findymail_name",
        "skrapp_find",
        "pattern_guess_zerobounce",
        "pattern_guess_abstract",
    }


def build_provider_chain() -> list[tuple[str, ProviderFn]]:
    """Ordered waterfall; omit any step whose env keys are missing."""

    chain: list[tuple[str, ProviderFn]] = []

    h_key = os.environ.get("HUNTER_API_KEY", "").strip()
    if h_key:

        def _h(row: LeadRow, domain: str) -> LookupOutcome:
            return hunter_lookup(domain, h_key, founder_name=(row.founder_name or "").strip())

        chain.append(("hunter", _h))

    snov_id = os.environ.get("SNOV_CLIENT_ID", "").strip()
    snov_secret = os.environ.get("SNOV_CLIENT_SECRET", "").strip()
    if snov_id and snov_secret:

        def _s(row: LeadRow, domain: str) -> LookupOutcome:
            return snov_lookup(domain, snov_id, snov_secret, founder_name=(row.founder_name or "").strip())

        chain.append(("snov", _s))

    apollo_key = os.environ.get("APOLLO_API_KEY", "").strip()
    if apollo_key:

        def _a(row: LeadRow, domain: str) -> LookupOutcome:
            return apollo_lookup(row, domain, apollo_key)

        chain.append(("apollo", _a))

    anymail_key = os.environ.get("ANYMAIL_FINDER_API_KEY", "").strip()
    if anymail_key:

        def _ac(row: LeadRow, domain: str) -> LookupOutcome:
            return anymail_company_lookup(row, domain, anymail_key)

        def _ap(row: LeadRow, domain: str) -> LookupOutcome:
            return anymail_person_lookup(row, domain, anymail_key)

        chain.append(("anymail_company", _ac))
        chain.append(("anymail_person", _ap))

    findymail_key = os.environ.get("FINDYMAIL_API_KEY", "").strip()
    if findymail_key:

        def _f(row: LeadRow, domain: str) -> LookupOutcome:
            return findymail_lookup(row, domain, findymail_key)

        chain.append(("findymail", _f))

    skrapp_key = os.environ.get("SKRAPP_API_KEY", "").strip()
    if skrapp_key:

        def _k(row: LeadRow, domain: str) -> LookupOutcome:
            return skrapp_lookup(row, domain, skrapp_key)

        chain.append(("skrapp", _k))

    return chain


def lookup_email_for_domain(row: LeadRow, domain: str, chain: list[tuple[str, ProviderFn]]) -> tuple[str | None, str]:
    last_source = "no_providers_configured"
    best_email: str | None = None
    best_source = last_source
    founder = (row.founder_name or "").strip()
    for i, (_name, fn) in enumerate(chain):
        if i:
            _sleep()
        try:
            out = fn(row, domain)
        except Exception:
            out = LookupOutcome(None, "provider_threw_exception", try_next=True)
        last_source = out.source
        if out.email:
            if not founder:
                return out.email, out.source
            if _person_specific_source(out.source) or email_matches_founder(out.email, founder):
                return out.email, out.source
            if generic_mailbox(out.email) and best_email is None:
                best_email, best_source = out.email, out.source
                continue
            if best_email is None:
                best_email, best_source = out.email, out.source
            continue
        if not out.try_next:
            return best_email, best_source if best_email else out.source
    if best_email:
        return best_email, best_source
    return None, last_source
