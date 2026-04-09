"""Create email drafts in the signed-in user's Outlook mailbox via Microsoft Graph."""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

from outreach.models import LeadRow

ROOT = Path(__file__).resolve().parent.parent
MSAL_CACHE_FILE = ROOT / "outreach_msal_cache.json"

GRAPH_MESSAGES = "https://graph.microsoft.com/v1.0/me/messages"
# Delegated scopes (v2)
GRAPH_SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/User.Read",
]


def outlook_client_help() -> str:
    return (
        "Add OUTLOOK_CLIENT_ID to your .env file (Azure “Application (client) ID” for a desktop app). "
        "Full steps: GETTING_STARTED.md → “Outlook”. "
        f"After sign-in, tokens are saved locally as {MSAL_CACHE_FILE.name}.\n\n"
        "Or use Google export, or Dry run."
    )


def outlook_client_id_configured() -> bool:
    return bool(os.environ.get("OUTLOOK_CLIENT_ID", "").strip())


def _public_app():
    from msal import PublicClientApplication
    from msal.token_cache import SerializableTokenCache

    client_id = os.environ.get("OUTLOOK_CLIENT_ID", "").strip()
    if not client_id:
        raise ValueError(outlook_client_help())
    tenant = (os.environ.get("OUTLOOK_TENANT_ID") or "common").strip() or "common"
    authority = f"https://login.microsoftonline.com/{tenant}"

    cache = SerializableTokenCache()
    if MSAL_CACHE_FILE.exists():
        try:
            cache.deserialize(MSAL_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    app = PublicClientApplication(
        client_id,
        authority=authority,
        token_cache=cache,
    )
    return app, cache


def acquire_graph_token() -> str:
    app, cache = _public_app()
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0])
    if not result:
        result = app.acquire_token_interactive(scopes=GRAPH_SCOPES)
    if cache.has_state_changed:
        MSAL_CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")
    if not result or "access_token" not in result:
        err = (result or {}).get("error_description") or (result or {}).get("error") or str(result)
        raise RuntimeError(f"Microsoft sign-in failed: {err}")
    return str(result["access_token"])


def _draft_body_for_row(row: LeadRow) -> str:
    body = (row.body or "").strip()
    if not (row.email or "").strip():
        body = "[Add recipient in To: — no email was found for this lead]\n\n" + body
    return body


def create_draft(
    token: str,
    subject: str,
    body: str,
    to_email: str | None,
    to_name: str | None,
) -> None:
    payload: dict = {
        "subject": (subject or "Outreach")[:255],
        "body": {"contentType": "Text", "content": body},
    }
    addr = (to_email or "").strip()
    if addr and "@" in addr:
        payload["toRecipients"] = [
            {
                "emailAddress": {
                    "address": addr,
                    "name": (to_name or "").strip() or addr,
                }
            }
        ]
    r = httpx.post(
        GRAPH_MESSAGES,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60.0,
    )
    if not r.is_success:
        raise RuntimeError(f"Graph API {r.status_code}: {r.text[:500]}")


def create_outlook_drafts_for_rows(
    rows: list[LeadRow],
    *,
    delay_sec: float = 0.35,
) -> int:
    token = acquire_graph_token()
    n = 0
    for i, row in enumerate(rows):
        if i > 0:
            time.sleep(delay_sec)
        body = _draft_body_for_row(row)
        create_draft(
            token,
            row.subject or "Outreach",
            body,
            row.email,
            row.founder_name or None,
        )
        n += 1
    return n
