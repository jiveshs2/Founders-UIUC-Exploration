from __future__ import annotations

import re

_ROLE_WORDS = {
    "founder",
    "cofounder",
    "co-founder",
    "ceo",
    "cto",
    "coo",
    "cfo",
    "president",
    "owner",
    "creator",
    "chairman",
    "chairwoman",
    "chief",
    "officer",
    "head",
    "director",
}

_GENERIC_LOCALS = {
    "admin",
    "bizdev",
    "careers",
    "community",
    "contact",
    "founders",
    "hello",
    "help",
    "hi",
    "info",
    "jobs",
    "media",
    "office",
    "partnerships",
    "press",
    "sales",
    "support",
    "team",
}


def founder_name_candidates(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = text.replace("|", ",").replace("•", ",").replace("+", ",")
    text = re.sub(r"\s+(?:and|with)\s+", ",", text, flags=re.I)
    text = re.sub(r"\s*&\s*", ",", text)
    parts = re.split(r"\s*[,/;]\s*", text)

    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = re.sub(r"[^A-Za-z .'\-]", " ", part)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
        if not cleaned:
            continue
        words = [w for w in cleaned.split() if w.lower() not in _ROLE_WORDS]
        if not words:
            continue
        name = " ".join(words).strip()
        low = name.lower()
        if low and low not in seen:
            seen.add(low)
            out.append(name)
    return out


def primary_founder_name(raw: str) -> str:
    names = founder_name_candidates(raw)
    return names[0] if names else (raw or "").strip()


def founder_name_pairs(raw: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for name in founder_name_candidates(raw):
        parts = [p.lower() for p in name.split() if p]
        if not parts:
            continue
        first = parts[0]
        last = parts[-1] if len(parts) > 1 else ""
        pairs.append((first, last))
    return pairs


def split_founder_name(raw: str) -> tuple[str, str]:
    pairs = founder_name_pairs(raw)
    return pairs[0] if pairs else ("", "")


def generic_mailbox(email: str) -> bool:
    local = (email.split("@", 1)[0] if "@" in email else email).lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", local) if t]
    return local in _GENERIC_LOCALS or any(t in _GENERIC_LOCALS for t in tokens)


def email_matches_founder(email: str, founder_raw: str) -> bool:
    local = (email.split("@", 1)[0] if "@" in email else email).lower()
    compact = re.sub(r"[^a-z0-9]", "", local)
    for first, last in founder_name_pairs(founder_raw):
        if not first:
            continue
        first_i = first[0]
        patterns = {
            first,
            f"{first}{last}",
            f"{first}.{last}",
            f"{first}_{last}",
            f"{first}-{last}",
            f"{first_i}{last}" if last else "",
            f"{first}{last[:1]}" if last else "",
            f"{first_i}.{last}" if last else "",
            f"{first}.{last[:1]}" if last else "",
        }
        patterns = {p for p in patterns if p}
        if local in patterns or compact in {re.sub(r"[^a-z0-9]", "", p) for p in patterns}:
            return True
        if last and first in compact and last in compact:
            return True
        if local == first:
            return True
    return False


def score_email_for_founder(email: str, founder_raw: str, domain: str) -> int:
    if "@" not in email:
        return -10_000
    dom = email.split("@", 1)[1].lower()
    target = (domain or "").lower().lstrip(".")
    score = 0
    if target and dom == target:
        score += 25
    elif target and dom.endswith("." + target):
        score += 15

    if email_matches_founder(email, founder_raw):
        score += 200
    elif generic_mailbox(email):
        score += 20
    elif founder_name_pairs(founder_raw):
        score -= 50
    return score
