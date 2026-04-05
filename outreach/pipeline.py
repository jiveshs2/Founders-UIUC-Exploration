from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from outreach.env_loader import groq_key_missing_message, load_environment
from outreach.enrich import enrich_rows_hunter
from outreach.extract import extract_rows_with_groq, fetch_page_text, normalize_page_url
from outreach.generate import generate_outreach_groq
from outreach.google_export import (
    create_doc_with_sections,
    create_sheet_with_rows,
    doc_url,
    sheet_url,
)
from outreach.models import LeadRow

HEADERS = [
    "founder_name",
    "company_name",
    "batch",
    "company_website",
    "email",
    "email_source",
    "status",
    "subject",
    "body",
]


def _sheet_row(row: LeadRow) -> list[str]:
    return [
        row.founder_name,
        row.company_name,
        row.batch,
        row.company_website,
        row.email or "",
        row.email_source or "",
        "draft",
        row.subject,
        row.body,
    ]


def _doc_section(row: LeadRow) -> str:
    lines = [
        f"=== {row.company_name or 'Unknown company'} ===",
        f"To: {row.email or '(no email — fill manually)'}",
        f"Founder: {row.founder_name or '—'}",
        f"Batch: {row.batch or '—'}",
        f"Website: {row.company_website or '—'}",
        "",
        f"Subject: {row.subject}",
        "",
        row.body,
    ]
    return "\n".join(lines)


@dataclass
class PipelineConfig:
    url: str
    extract_prompt: str
    purpose_prompt: str
    name_prefix: str = ""
    sheet_title: str | None = None
    doc_title: str | None = None
    dry_run: bool = False


@dataclass
class PipelineResult:
    success: bool
    exit_code: int
    sheet_url: str | None = None
    doc_url: str | None = None
    dry_run_text: str | None = None
    error: str | None = None
    extract_debug: str | None = None
    rows_count: int = 0
    logs: list[str] = field(default_factory=list)


def run_pipeline(cfg: PipelineConfig, log_to_stderr: bool = True) -> PipelineResult:
    logs: list[str] = []

    def log(msg: str) -> None:
        logs.append(msg)
        if log_to_stderr:
            print(msg, file=sys.stderr)

    load_environment()
    if not os.environ.get("GROQ_API_KEY", "").strip():
        return PipelineResult(
            success=False,
            exit_code=1,
            error=groq_key_missing_message(),
            logs=logs,
        )

    try:
        page_url = normalize_page_url(cfg.url)
    except ValueError as e:
        return PipelineResult(success=False, exit_code=1, error=str(e), logs=logs)

    log("Fetching page…")
    try:
        page_text = fetch_page_text(page_url)
    except ValueError as e:
        return PipelineResult(success=False, exit_code=1, error=str(e), logs=logs)

    log("Extracting rows with Groq…")
    extracted = extract_rows_with_groq(page_text, cfg.extract_prompt, page_url)
    if not extracted.rows:
        debug = (extracted.raw_model_text or "")[:8000]
        log("No rows extracted.")
        return PipelineResult(
            success=False,
            exit_code=1,
            error="No rows extracted from the page. Try a clearer extract prompt or a different URL.",
            extract_debug=debug,
            logs=logs,
        )

    log(f"Extracted {len(extracted.rows)} row(s). Enriching emails…")
    cache: dict[str, tuple[str | None, str | None]] = {}
    rows = enrich_rows_hunter(extracted.rows, cache=cache)

    log("Generating outreach with Groq…")
    for i, row in enumerate(rows):
        if i > 0:
            time.sleep(0.4)
        subj, body = generate_outreach_groq(row, cfg.purpose_prompt)
        row.subject = subj
        row.body = body

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    base = cfg.name_prefix or "Outreach run"
    sheet_title = cfg.sheet_title or f"{base} — {stamp}"
    doc_title = cfg.doc_title or f"{base} drafts — {stamp}"

    if cfg.dry_run:
        parts: list[str] = []
        for row in rows:
            parts.append(_doc_section(row))
            parts.append("\n" + "-" * 40 + "\n")
        log("Dry run: skipped Google Sheets / Docs.")
        return PipelineResult(
            success=True,
            exit_code=0,
            dry_run_text="\n".join(parts),
            rows_count=len(rows),
            logs=logs,
        )

    log("Creating Google Sheet…")
    try:
        sheet_values = [_sheet_row(r) for r in rows]
        sid = create_sheet_with_rows(sheet_title, HEADERS, sheet_values)
    except Exception as e:
        return PipelineResult(
            success=False,
            exit_code=1,
            error=f"Google Sheets failed: {e}",
            rows_count=len(rows),
            logs=logs,
        )

    log("Creating Google Doc…")
    try:
        sections = [_doc_section(r) for r in rows]
        did = create_doc_with_sections(doc_title, sections)
    except Exception as e:
        return PipelineResult(
            success=False,
            exit_code=1,
            error=f"Google Docs failed: {e}",
            rows_count=len(rows),
            logs=logs,
        )

    su, du = sheet_url(sid), doc_url(did)
    log(su)
    log(du)
    return PipelineResult(
        success=True,
        exit_code=0,
        sheet_url=su,
        doc_url=du,
        rows_count=len(rows),
        logs=logs,
    )
