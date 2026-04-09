"""Local web UI + API for the outreach pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from outreach.env_loader import load_environment
from outreach.pipeline import normalize_export_mode
from outreach.prompts import TONE_OPTIONS

load_environment()

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Outreach automation", version="0.1.0")


class RunRequest(BaseModel):
    url: str = Field(..., description="Page to fetch")
    scope_hint: str = Field(
        ...,
        min_length=1,
        description="Which companies to include (batch, filters). Not spreadsheet columns.",
    )
    event_description: str = Field(
        ...,
        min_length=1,
        description="Event or ask you are emailing about",
    )
    whats_in_it_for_them: str = Field(
        default="",
        description="What’s in it for them to come? Used to strengthen the value proposition.",
    )
    tones: list[str] = Field(default_factory=list, description="Email tone tags from UI")
    sign_off: str = Field(
        default="",
        description="Appended to every generated email body (respects word limit).",
    )
    max_words: int | None = Field(
        default=None,
        ge=20,
        le=400,
        description="Optional cap on email body length in words (e.g. 80, 120).",
    )
    name_prefix: str = ""
    sheet_title: str | None = None
    doc_title: str | None = None
    export_mode: str = Field(default="outlook", description="outlook | google")
    dry_run: bool = False
    max_rows: int | None = Field(default=None, ge=1, le=500, description="Cap rows after extract, e.g. 5")

    @field_validator("export_mode", mode="before")
    @classmethod
    def _export_mode(cls, v: object) -> str:
        return normalize_export_mode(str(v) if v is not None else None)

    @field_validator("tones", mode="before")
    @classmethod
    def _tones(cls, v: object) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        allowed = {t.lower() for t in TONE_OPTIONS}
        return [str(t).strip().lower() for t in v if str(t).strip().lower() in allowed]


class RunResponse(BaseModel):
    success: bool
    rows_count: int = 0
    sheet_url: str | None = None
    doc_url: str | None = None
    outlook_drafts_count: int = 0
    dry_run_text: str | None = None
    error: str | None = None
    extract_debug: str | None = None
    logs: list[str] = []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def serve_ui():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "UI not found")
    return FileResponse(
        index,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.post("/api/run", response_model=RunResponse)
async def api_run(body: RunRequest) -> RunResponse:
    from outreach.pipeline import PipelineConfig, PipelineResult, run_pipeline

    cfg = PipelineConfig(
        url=body.url.strip(),
        scope_hint=body.scope_hint.strip(),
        event_description=body.event_description.strip(),
        whats_in_it_for_them=(body.whats_in_it_for_them or "").strip(),
        tones=body.tones,
        sign_off=(body.sign_off or "").strip(),
        max_words=body.max_words,
        name_prefix=body.name_prefix.strip(),
        sheet_title=body.sheet_title.strip() if body.sheet_title else None,
        doc_title=body.doc_title.strip() if body.doc_title else None,
        export_mode=body.export_mode,
        dry_run=body.dry_run,
        max_rows=body.max_rows,
    )

    loop = asyncio.get_running_loop()

    def _run() -> PipelineResult:
        try:
            return run_pipeline(cfg, log_to_stderr=True)
        except Exception as e:
            return PipelineResult(success=False, exit_code=1, error=f"Unexpected error: {e}", logs=[])

    result = await loop.run_in_executor(None, _run)
    return RunResponse(
        success=result.success,
        rows_count=result.rows_count,
        sheet_url=result.sheet_url,
        doc_url=result.doc_url,
        outlook_drafts_count=result.outlook_drafts_count,
        dry_run_text=result.dry_run_text,
        error=result.error,
        extract_debug=result.extract_debug,
        logs=result.logs,
    )


def run_web_server() -> None:
    import uvicorn

    uvicorn.run("outreach.web:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    run_web_server()
