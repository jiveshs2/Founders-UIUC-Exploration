from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class LeadRow(BaseModel):
    """Normalized row after extraction; optional fields filled during enrichment / generation."""

    founder_name: str = ""
    company_name: str = ""
    batch: str = ""
    company_website: str = ""
    notes: str = ""

    email: str | None = None
    email_source: str | None = None
    subject: str = ""
    body: str = ""

    model_config = {"extra": "allow"}

    @field_validator("company_website", mode="before")
    @classmethod
    def normalize_url(cls, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        if not s:
            return ""
        if s.startswith("//"):
            return f"https:{s}"
        if not s.startswith(("http://", "https://")):
            return f"https://{s}"
        return s

    def domain(self) -> str | None:
        if not self.company_website:
            return None
        try:
            host = urlparse(self.company_website).netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            return host or None
        except Exception:
            return None


class ExtractResult(BaseModel):
    rows: list[LeadRow] = Field(default_factory=list)
    raw_model_text: str = ""
