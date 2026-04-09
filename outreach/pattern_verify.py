"""Guess common corporate formats and optionally verify with free-tier APIs (B)."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Callable

import httpx

from outreach.founder_names import founder_name_pairs


def split_founder_name(full: str) -> tuple[str, str]:
    pairs = founder_name_pairs(full)
    return pairs[0] if pairs else ("", "")


def candidate_emails(first: str, last: str, domain: str) -> list[str]:
    first = (first or "").strip().lower()
    last = (last or "").strip().lower()
    d = (domain or "").strip().lower().strip(".")
    if not first or not d:
        return []
    li = last[0] if last else ""
    fi = first[0] if first else ""
    seq: list[str] = []
    if last:
        seq = [
            f"{first}@{d}",
            f"{first}.{last}@{d}",
            f"{fi}{last}@{d}",
            f"{first}{last}@{d}",
            f"{first}_{last}@{d}",
            f"{first}-{last}@{d}",
            f"{first}{li}@{d}",
        ]
    else:
        seq = [f"{first}@{d}", f"{fi}@{d}"]
    seen: set[str] = set()
    out: list[str] = []
    for c in seq:
        cl = c.lower()
        if cl not in seen:
            seen.add(cl)
            out.append(cl)
    return out


def _zb_acceptable(data: dict) -> bool | None:
    status = str(data.get("status") or "").lower()
    if status in ("valid", "catch-all"):
        return True
    if status in ("invalid", "spamtrap", "abuse", "do_not_mail"):
        return False
    return None


def _abstract_acceptable(data: dict) -> bool | None:
    raw = data.get("is_deliverable")
    if isinstance(raw, dict):
        raw = raw.get("value")
    if raw is True:
        return True
    if raw is False:
        return False
    text = str(data.get("deliverability") or data.get("quality_score") or "").upper()
    if "UNDELIVERABLE" in text:
        return False
    if "DELIVERABLE" in text:
        return True
    return None


VerifierFn = Callable[[str], bool | None]


def _build_verifier_chain() -> list[tuple[str, VerifierFn]]:
    chain: list[tuple[str, VerifierFn]] = []
    zb_key = os.environ.get("ZEROBOUNCE_API_KEY", "").strip()
    if zb_key:

        def zb_verify(email: str) -> bool | None:
            try:
                with httpx.Client(timeout=35.0) as client:
                    r = client.get(
                        "https://api.zerobounce.net/v2/validate",
                        params={"api_key": zb_key, "email": email},
                    )
                if not r.is_success:
                    return None
                data = r.json()
                if not isinstance(data, dict):
                    return None
                return _zb_acceptable(data)
            except (httpx.HTTPError, json.JSONDecodeError, OSError):
                return None

        chain.append(("zerobounce", zb_verify))

    abs_key = os.environ.get("ABSTRACT_EMAIL_VALIDATION_API_KEY", "").strip()
    if abs_key:

        def ab_verify(email: str) -> bool | None:
            try:
                with httpx.Client(timeout=35.0) as client:
                    r = client.get(
                        "https://emailvalidation.abstractapi.com/v1/",
                        params={"api_key": abs_key, "email": email},
                    )
                if not r.is_success:
                    return None
                data = r.json()
                if not isinstance(data, dict):
                    return None
                return _abstract_acceptable(data)
            except (httpx.HTTPError, json.JSONDecodeError, OSError):
                return None

        chain.append(("abstract", ab_verify))

    return chain


def try_pattern_verified_email(first: str, last: str, domain: str, founder_raw: str = "") -> tuple[str | None, str]:
    """
    If at least one verification API key is set, try guessed addresses in order
    until a verifier returns True. Without keys, returns (None, …).
    """
    v = os.environ.get("OUTREACH_PATTERN_GUESS", "1").strip().lower()
    if v in ("0", "false", "no", "off"):
        return None, "pattern_guess_disabled"

    verifiers = _build_verifier_chain()
    if not verifiers:
        return None, "pattern_verify_no_api_keys"

    candidates = candidate_emails(first, last, domain)
    if founder_raw:
        for fn, ln in founder_name_pairs(founder_raw):
            for em in candidate_emails(fn, ln, domain):
                if em not in candidates:
                    candidates.append(em)
    if not candidates:
        return None, "pattern_no_candidates"

    delay = 0.35
    for i, em in enumerate(candidates):
        if i:
            time.sleep(delay)
        for vname, fn in verifiers:
            try:
                ok = fn(em)
            except Exception:
                ok = None
            if ok is True:
                return em, f"pattern_guess_{vname}"
            if ok is False:
                break
    return None, "pattern_verify_no_match"
