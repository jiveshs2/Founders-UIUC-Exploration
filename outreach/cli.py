from __future__ import annotations

import argparse
import sys

from outreach.pipeline import PipelineConfig, run_pipeline


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)
    if argv and argv[0] == "run":
        argv = argv[1:]

    p = argparse.ArgumentParser(
        description="Extract leads from a URL, enrich emails, generate Founders outreach, export to Outlook drafts or Google.",
    )
    p.add_argument(
        "--url",
        required=True,
        help="Page URL to fetch (https:// added if omitted)",
    )
    p.add_argument(
        "--scope-hint",
        default=None,
        help="Which companies to include (e.g. 'Fall 2025 batch only'). Not column names — schema is fixed. "
        "Use with --event-description unless you use advanced --extract-prompt.",
    )
    p.add_argument(
        "--event-description",
        default=None,
        help="What you're inviting them to / the ask (event, partnership, etc.). "
        "Use with --scope-hint unless you use advanced --purpose-prompt.",
    )
    p.add_argument(
        "--whats-in-it-for-them",
        default="",
        help="Optional: value proposition for them to come (fed into the prompt).",
    )
    p.add_argument(
        "--tones",
        default=None,
        help="Comma-separated tones from the UI list in the web app (optional; defaults apply if omitted). "
        "Example: 'professional,warm,direct' or 'urgent but polite'.",
    )
    p.add_argument(
        "--sign-off",
        default="",
        help="Optional: appended to every email body (respects word limit).",
    )
    p.add_argument(
        "--max-words",
        type=int,
        default=None,
        help="Optional cap on email body length in words (e.g. 80, 120). If omitted, defaults to 100.",
    )
    p.add_argument(
        "--extract-prompt",
        default=None,
        help="Advanced: full extraction instructions (overrides --scope-hint). Must pair with --purpose-prompt.",
    )
    p.add_argument(
        "--purpose-prompt",
        default=None,
        help="Advanced: full email-generation brief (overrides --event-description and --tones). "
        "Must pair with --extract-prompt.",
    )
    p.add_argument(
        "--name-prefix",
        default="",
        help="Short label for default Sheet/Doc titles",
    )
    p.add_argument("--sheet-title", default=None, help="Override spreadsheet title")
    p.add_argument("--doc-title", default=None, help="Override document title")
    p.add_argument(
        "--export",
        choices=["outlook", "google"],
        default=None,
        help="outlook (default): Microsoft Graph drafts. google: Sheet + Doc. "
        "Override with OUTREACH_EXPORT in .env.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip export; print drafts to stdout",
    )
    p.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Keep only the first N companies after extraction (e.g. 5). Zero or negative means no limit.",
    )
    args = p.parse_args(argv)
    if args.max_rows is not None and args.max_rows <= 0:
        args.max_rows = None

    legacy = bool(
        args.extract_prompt
        and args.extract_prompt.strip()
        and args.purpose_prompt
        and args.purpose_prompt.strip()
    )
    new_mode = bool(
        args.scope_hint
        and args.scope_hint.strip()
        and args.event_description
        and args.event_description.strip()
    )

    if legacy and new_mode:
        p.error("Use either (--scope-hint + --event-description) OR (--extract-prompt + --purpose-prompt), not both.")
    if not legacy and not new_mode:
        p.error(
            "Provide --scope-hint and --event-description, "
            "or for advanced use both --extract-prompt and --purpose-prompt."
        )

    tones: list[str] = []
    if args.tones:
        tones = [t.strip().lower() for t in args.tones.split(",") if t.strip()]

    if legacy:
        cfg = PipelineConfig(
            url=args.url,
            extract_prompt_override=args.extract_prompt.strip(),
            purpose_prompt_override=args.purpose_prompt.strip(),
            name_prefix=args.name_prefix,
            sheet_title=args.sheet_title,
            doc_title=args.doc_title,
            export_mode=args.export,
            dry_run=args.dry_run,
            max_rows=args.max_rows,
        )
    else:
        cfg = PipelineConfig(
            url=args.url,
            scope_hint=args.scope_hint.strip(),
            event_description=args.event_description.strip(),
            whats_in_it_for_them=(args.whats_in_it_for_them or "").strip(),
            tones=tones,
            sign_off=(args.sign_off or "").strip(),
            max_words=args.max_words,
            name_prefix=args.name_prefix,
            sheet_title=args.sheet_title,
            doc_title=args.doc_title,
            export_mode=args.export,
            dry_run=args.dry_run,
            max_rows=args.max_rows,
        )

    result = run_pipeline(cfg, log_to_stderr=True)
    if result.dry_run_text:
        print(result.dry_run_text)
    if result.extract_debug and not result.success:
        print(result.extract_debug, file=sys.stderr)
    if result.error and not result.success:
        print(result.error, file=sys.stderr)
    raise SystemExit(result.exit_code)


if __name__ == "__main__":
    main()
