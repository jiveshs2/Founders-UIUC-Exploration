"""Infer a company domain from its name when no website URL was extracted."""

from __future__ import annotations

import re
import socket


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[''`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


_TLD_ORDER = (
    ".com", ".dev", ".io", ".co", ".ai", ".app", ".tech",
    ".org", ".net", ".xyz", ".so", ".sh",
)


def _candidates(name: str) -> list[str]:
    slug = _slugify(name)
    if not slug:
        return []
    parts = name.lower().strip().split()
    hyphenated = "-".join(re.sub(r"[^a-z0-9]", "", p) for p in parts if p).strip("-")

    seen: set[str] = set()
    out: list[str] = []

    for tld in _TLD_ORDER:
        c = f"{slug}{tld}"
        if c not in seen:
            seen.add(c)
            out.append(c)

    for prefix in ("get", "try", "use"):
        c = f"{prefix}{slug}.com"
        if c not in seen:
            seen.add(c)
            out.append(c)
    for suffix in ("app", "hq"):
        c = f"{slug}{suffix}.com"
        if c not in seen:
            seen.add(c)
            out.append(c)
    if hyphenated and hyphenated != slug:
        for tld in (".com", ".dev", ".io"):
            c = f"{hyphenated}{tld}"
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


def _dns_resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        return True
    except (socket.gaierror, OSError):
        return False


def guess_domain(company_name: str) -> str | None:
    """Return the first candidate domain that resolves via DNS, or None."""
    all_resolving = guess_domains(company_name)
    return all_resolving[0] if all_resolving else None


def guess_domains(company_name: str) -> list[str]:
    """Return ALL candidate domains that resolve via DNS (ordered by likelihood)."""
    name = (company_name or "").strip()
    if not name or len(name) < 2:
        return []
    return [c for c in _candidates(name) if _dns_resolves(c)]
