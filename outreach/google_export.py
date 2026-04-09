from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
)

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = ROOT / "credentials.json"
TOKEN_FILE = ROOT / "token.json"


def google_credentials_help() -> str:
    """Human-readable steps when credentials.json is missing."""
    return (
        f"Google export needs credentials.json in:\n  {CREDENTIALS_FILE}\n\n"
        "That file comes from Google Cloud (Desktop OAuth client). "
        "Step-by-step: open GETTING_STARTED.md in this project → section “Google credentials.json”.\n\n"
        "Or use Dry run to preview without Google."
    )


def credentials_ready() -> bool:
    return CREDENTIALS_FILE.is_file()


def get_credentials() -> Credentials:
    creds: Credentials | None = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            creds = None
            try:
                TOKEN_FILE.unlink(missing_ok=True)
            except OSError:
                pass
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
                try:
                    TOKEN_FILE.unlink(missing_ok=True)
                except OSError:
                    pass
        if not creds or not creds.valid:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(google_credentials_help()) from None
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def create_sheet_with_rows(title: str, headers: list[str], rows: list[list[str]]) -> str:
    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    spreadsheet = (
        sheets.spreadsheets()
        .create(
            body={"properties": {"title": title}},
            fields="spreadsheetId",
        )
        .execute()
    )
    sid = spreadsheet["spreadsheetId"]
    values = [headers] + rows
    sheets.spreadsheets().values().update(
        spreadsheetId=sid,
        range="Sheet1!A1",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()
    return sid


def create_doc_with_sections(title: str, sections: list[str]) -> str:
    creds = get_credentials()
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)
    doc = docs.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    full_text = "\n\n".join(sections)
    if not full_text:
        full_text = "(no content)"
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": full_text,
                    }
                }
            ]
        },
    ).execute()
    return doc_id


def sheet_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"


def doc_url(document_id: str) -> str:
    return f"https://docs.google.com/document/d/{document_id}/edit"
