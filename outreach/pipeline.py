from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from outreach.env_loader import groq_key_missing_message, load_environment, project_root
from outreach.contact_scrape import pick_best_email
from outreach.enrich import enrich_rows_email
from outreach.extract import (
    extract_yc_company_detail,
    extract_rows_with_gemini,
    extract_rows_with_groq,
    fetch_page_text_and_html,
    normalize_page_url,
    recover_company_websites,
)
from outreach.html_emails import extract_emails_from_html
from outreach.generate import generate_outreach_gemini, generate_outreach_groq
from outreach.google_export import (
    create_doc_with_sections,
    create_sheet_with_rows,
    credentials_ready,
    doc_url,
    google_credentials_help,
    sheet_url,
)
from outreach.models import LeadRow
from outreach.outlook_export import (
    create_outlook_drafts_for_rows,
    outlook_client_id_configured,
)
from outreach.prompts import build_extract_prompt, build_purpose_prompt, normalize_tones


def normalize_export_mode(mode: str | None) -> str:
    m = (mode or os.environ.get("OUTREACH_EXPORT") or "outlook").strip().lower()
    if m in ("google", "sheets", "gdoc", "docs", "sheet"):
        return "google"
    return "outlook"


def export_prerequisite_error() -> str:
    env_path = project_root() / ".env"
    return (
        "To save results (not Dry run), set up ONE of the following:\n\n"
        "• Outlook — add OUTLOOK_CLIENT_ID to your .env file\n"
        "• Google — add credentials.json to the project folder and pick Google export\n\n"
        f"Config file: {env_path}\n"
        "Step-by-step: open GETTING_STARTED.md in this project folder.\n\n"
        "Tip: use Dry run to preview emails without Outlook or Google."
    )


def _safe_float_env(name: str, default: float, floor: float = 0.0) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return max(floor, v)


def _groq_failure_message(phase: str, exc: BaseException) -> str:
    msg = str(exc).strip()
    hint = ""
    low = msg.lower()
    if "413" in msg or "too large" in low or "token" in low:
        hint = (
            " Groq rejected the request size or TPM limit. "
            "Try a smaller page URL (e.g. a single batch page), shorten or broaden your inclusion filter, "
            "or set GROQ_MAX_PAGE_CHARS lower in .env. "
            "See https://console.groq.com/settings/billing for higher limits."
        )
    elif "429" in msg or "rate" in low:
        hint = (
            " Rate limit hit. Wait a minute and retry, increase GROQ_ROW_DELAY_SEC in .env, "
            "or reduce how many rows you extract at once."
        )
    return f"Groq error during {phase}: {msg}.{hint}"


def _combined_llm_failure_message(
    phase: str,
    primary_name: str,
    primary_exc: BaseException,
    fallback_name: str | None = None,
    fallback_exc: BaseException | None = None,
) -> str:
    primary = f"{primary_name} error during {phase}: {str(primary_exc).strip()}"
    if fallback_name and fallback_exc is not None:
        fallback = f"{fallback_name} fallback also failed during {phase}: {str(fallback_exc).strip()}"
        return f"{primary}\n{fallback}"
    return primary


HEADERS = [
    "company_name",
    "founder_name",
    "industry",
    "company_website",
    "email",
    "email_source",
    "status",
    "subject",
    "body",
]


def _sheet_row(row: LeadRow) -> list[str]:
    return [
        row.company_name,
        row.founder_name,
        row.industry,
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
        f"Industry: {row.industry or '—'}",
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
    scope_hint: str = ""
    event_description: str = ""
    whats_in_it_for_them: str = ""
    tones: list[str] = field(default_factory=list)
    """If set, used instead of building from scope_hint / event_description / tones."""
    extract_prompt_override: str | None = None
    purpose_prompt_override: str | None = None
    sign_off: str = ""
    max_words: int | None = None
    name_prefix: str = ""
    sheet_title: str | None = None
    doc_title: str | None = None
    """None → OUTREACH_EXPORT env or outlook. google: Sheet + Doc."""
    export_mode: str | None = None
    dry_run: bool = False
    max_rows: int | None = None

    def resolved_extract_prompt(self) -> str:
        if self.extract_prompt_override and self.extract_prompt_override.strip():
            return self.extract_prompt_override.strip()
        base = build_extract_prompt(self.scope_hint)
        if self.max_rows is not None and self.max_rows > 0:
            return f"""Additional constraint: return at most {self.max_rows} row(s) total.

{base}"""
        return base

    def resolved_purpose_prompt(self) -> str:
        if self.purpose_prompt_override and self.purpose_prompt_override.strip():
            return self.purpose_prompt_override.strip()
        return build_purpose_prompt(self.event_description, self.whats_in_it_for_them, normalize_tones(self.tones))


@dataclass
class PipelineResult:
    success: bool
    exit_code: int
    sheet_url: str | None = None
    doc_url: str | None = None
    outlook_drafts_count: int = 0
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
    if not (os.environ.get("GROQ_API_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()):
        return PipelineResult(
            success=False,
            exit_code=1,
            error=(
                groq_key_missing_message()
                + "\n\nAlternatively, set GEMINI_API_KEY in your .env to use Gemini instead of Groq."
            ),
            logs=logs,
        )

    export_mode = normalize_export_mode(cfg.export_mode)
    if not cfg.dry_run:
        if (
            export_mode == "outlook"
            and not outlook_client_id_configured()
            and credentials_ready()
        ):
            log(
                "Outlook isn’t configured in .env — using Google (credentials.json found). "
                "Add OUTLOOK_CLIENT_ID to use Outlook."
            )
            export_mode = "google"
        if export_mode == "google" and not credentials_ready():
            return PipelineResult(
                success=False,
                exit_code=1,
                error=google_credentials_help(),
                logs=logs,
            )
        if export_mode == "outlook" and not outlook_client_id_configured():
            return PipelineResult(
                success=False,
                exit_code=1,
                error=export_prerequisite_error(),
                logs=logs,
            )

    try:
        page_url = normalize_page_url(cfg.url)
    except ValueError as e:
        return PipelineResult(success=False, exit_code=1, error=str(e), logs=logs)

    log("Fetching page…")
    try:
        page_text, page_html = fetch_page_text_and_html(page_url)
    except ValueError as e:
        return PipelineResult(success=False, exit_code=1, error=str(e), logs=logs)

    list_page_emails: list[str] = []
    if os.environ.get("OUTREACH_LIST_PAGE_EMAILS", "1").strip().lower() not in ("0", "false", "no", "off"):
        list_page_emails = extract_emails_from_html(page_html or "")

    has_groq = bool(os.environ.get("GROQ_API_KEY", "").strip())
    has_gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip())

    log("Extracting rows…")
    extract_provider = "groq" if has_groq else "gemini"
    yc_extracted = extract_yc_company_detail(page_html, page_url)
    if yc_extracted and yc_extracted.rows:
        extracted = yc_extracted
        extract_provider = "yc_parser"
    else:
        try:
            if has_groq:
                extracted = extract_rows_with_groq(page_text, cfg.resolved_extract_prompt(), page_url)
            else:
                extracted = extract_rows_with_gemini(page_text, cfg.resolved_extract_prompt(), page_url)
        except Exception as e:
            if has_gemini and has_groq:
                log("Groq extract failed; trying Gemini fallback…")
                try:
                    extracted = extract_rows_with_gemini(page_text, cfg.resolved_extract_prompt(), page_url)
                    extract_provider = "gemini_fallback"
                except Exception as ge:
                    return PipelineResult(
                        success=False,
                        exit_code=1,
                        error=_combined_llm_failure_message("extract", "Groq", e, "Gemini", ge),
                        logs=logs,
                    )
            else:
                return PipelineResult(
                    success=False,
                    exit_code=1,
                    error=_groq_failure_message("extract", e),
                    logs=logs,
                )
    if not extracted.rows:
        debug = (extracted.raw_model_text or "")[:12000]
        log("No rows extracted.")
        log(f"Extractor used: {extract_provider}.")
        hints: list[str] = []
        if len(page_text.strip()) < 800:
            hints.append(
                "The downloaded page text is very short — many sites load lists with JavaScript, "
                "so a plain fetch may see almost nothing. Try a simpler HTML page, a batch-specific URL, "
                "or paste content into a static page you control."
            )
        low = debug.lower()
        if "parse error" in low or ("json" in low and "error" in low):
            hints.append("Groq’s reply may not have been valid JSON; check the debug snippet below.")
        elif "[]" in debug[:400].replace(" ", ""):
            hints.append(
                "The model returned an empty list — broaden who to include or confirm the page lists those companies in the fetched text."
            )
        else:
            hints.append(
                "Try a shorter, more specific URL; relax the inclusion rules; or open the debug output to see what the model returned."
            )
        return PipelineResult(
            success=False,
            exit_code=1,
            error="No rows extracted. " + " ".join(hints),
            extract_debug=debug,
            logs=logs,
        )

    rows_list = list(extracted.rows)
    log(f"Extractor used: {extract_provider}.")
    max_rows = cfg.max_rows if cfg.max_rows is not None and cfg.max_rows > 0 else None
    if max_rows is not None:
        rows_list = rows_list[:max_rows]
        log(f"Limited to first {max_rows} row(s).")

    rows_list = recover_company_websites(rows_list, page_text, page_url, page_html)

    if list_page_emails:
        for row in rows_list:
            if row.email:
                continue
            dom = row.domain()
            if not dom:
                continue
            dom_l = dom.lower()
            on_page = [
                e
                for e in list_page_emails
                if e.lower().split("@")[-1] == dom_l or e.lower().endswith("." + dom_l)
            ]
            if not on_page:
                continue
            best = pick_best_email(on_page, row.founder_name or "", dom)
            if best:
                row.email = best
                row.email_source = "list_page_html"

    log(f"Extracted {len(rows_list)} row(s). Enriching emails…")
    cache: dict[str, tuple[str | None, str | None]] = {}
    rows = enrich_rows_email(rows_list, cache=cache)
    for row in rows:
        log(
            f"Email result: {row.company_name or 'Unknown'} -> "
            f"{row.email or '(none)'} [{row.email_source or 'unknown'}]"
        )

    log("Generating outreach…")
    generation_provider = "groq" if has_groq else "gemini"
    row_delay = _safe_float_env("GROQ_ROW_DELAY_SEC", 0.85, floor=0.2)
    for i, row in enumerate(rows):
        if i > 0:
            time.sleep(max(0.2, row_delay))
        try:
            if has_groq:
                subj, body = generate_outreach_groq(
                    row,
                    cfg.resolved_purpose_prompt(),
                    sign_off=cfg.sign_off,
                    max_words=cfg.max_words,
                )
            else:
                subj, body = generate_outreach_gemini(
                    row,
                    cfg.resolved_purpose_prompt(),
                    sign_off=cfg.sign_off,
                    max_words=cfg.max_words,
                )
        except Exception as e:
            if has_gemini and has_groq:
                log("Groq generation failed; trying Gemini fallback…")
                try:
                    subj, body = generate_outreach_gemini(
                        row,
                        cfg.resolved_purpose_prompt(),
                        sign_off=cfg.sign_off,
                        max_words=cfg.max_words,
                    )
                    generation_provider = "gemini_fallback"
                except Exception as ge:
                    return PipelineResult(
                        success=False,
                        exit_code=1,
                        error=_combined_llm_failure_message("generate", "Groq", e, "Gemini", ge),
                        rows_count=len(rows),
                        logs=logs,
                    )
            else:
                return PipelineResult(
                    success=False,
                    exit_code=1,
                    error=_groq_failure_message("generate", e),
                    rows_count=len(rows),
                    logs=logs,
                )
        row.subject = subj
        row.body = body
    log(f"Generator used: {generation_provider}.")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    base = cfg.name_prefix or "Outreach run"
    sheet_title = cfg.sheet_title or f"{base} — {stamp}"
    doc_title = cfg.doc_title or f"{base} drafts — {stamp}"

    if cfg.dry_run:
        parts: list[str] = []
        for row in rows:
            parts.append(_doc_section(row))
            parts.append("\n" + "-" * 40 + "\n")
        log("Dry run: skipped export (no Outlook drafts or Google Sheet/Doc).")
        return PipelineResult(
            success=True,
            exit_code=0,
            dry_run_text="\n".join(parts),
            rows_count=len(rows),
            logs=logs,
        )

    if export_mode == "outlook":
        log("Creating Outlook drafts (Microsoft Graph)…")
        try:
            n = create_outlook_drafts_for_rows(rows)
        except ValueError as e:
            return PipelineResult(
                success=False,
                exit_code=1,
                error=str(e),
                rows_count=len(rows),
                logs=logs,
            )
        except Exception as e:
            return PipelineResult(
                success=False,
                exit_code=1,
                error=f"Outlook export failed: {e}",
                rows_count=len(rows),
                logs=logs,
            )
        log(f"Created {n} draft(s). Open Outlook → Drafts to review and send.")
        return PipelineResult(
            success=True,
            exit_code=0,
            outlook_drafts_count=n,
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
