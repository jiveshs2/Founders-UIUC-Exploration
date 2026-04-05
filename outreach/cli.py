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

    p = argparse.ArgumentParser(description="Extract leads, enrich, generate outreach, export to Google.")
    p.add_argument(
        "--url",
        required=True,
        help="Page URL to fetch (https:// added automatically if you omit the scheme)",
    )
    p.add_argument(
        "--extract-prompt",
        required=True,
        help="Natural language: what to pull from the page (e.g. batch, fields)",
    )
    p.add_argument(
        "--purpose-prompt",
        required=True,
        help="Why you are reaching out; used to draft each email",
    )
    p.add_argument(
        "--name-prefix",
        default="",
        help="Short label used in default Sheet/Doc titles",
    )
    p.add_argument("--sheet-title", default=None, help="Override spreadsheet title")
    p.add_argument("--doc-title", default=None, help="Override document title")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call Google APIs; print draft sections to stdout",
    )
    args = p.parse_args(argv)

    cfg = PipelineConfig(
        url=args.url,
        extract_prompt=args.extract_prompt,
        purpose_prompt=args.purpose_prompt,
        name_prefix=args.name_prefix,
        sheet_title=args.sheet_title,
        doc_title=args.doc_title,
        dry_run=args.dry_run,
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
