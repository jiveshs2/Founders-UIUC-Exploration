"""Local web UI + API for the outreach pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from outreach.env_loader import load_environment

load_environment()

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Outreach automation", version="0.1.0")


class RunRequest(BaseModel):
    url: str = Field(..., description="Page to fetch")
    extract_prompt: str = Field(..., min_length=1, description="What to pull from the page")
    purpose_prompt: str = Field(..., min_length=1, description="Why you are reaching out")
    name_prefix: str = ""
    sheet_title: str | None = None
    doc_title: str | None = None
    dry_run: bool = False


class RunResponse(BaseModel):
    success: bool
    rows_count: int = 0
    sheet_url: str | None = None
    doc_url: str | None = None
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
    return FileResponse(index)


@app.post("/api/run", response_model=RunResponse)
async def api_run(body: RunRequest) -> RunResponse:
    from outreach.pipeline import PipelineConfig, run_pipeline

    cfg = PipelineConfig(
        url=body.url.strip(),
        extract_prompt=body.extract_prompt.strip(),
        purpose_prompt=body.purpose_prompt.strip(),
        name_prefix=body.name_prefix.strip(),
        sheet_title=body.sheet_title.strip() if body.sheet_title else None,
        doc_title=body.doc_title.strip() if body.doc_title else None,
        dry_run=body.dry_run,
    )

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: run_pipeline(cfg, log_to_stderr=True))

    return RunResponse(
        success=result.success,
        rows_count=result.rows_count,
        sheet_url=result.sheet_url,
        doc_url=result.doc_url,
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
