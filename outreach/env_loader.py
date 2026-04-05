"""Load .env from the project root (not only the current working directory)."""

from __future__ import annotations

import os
from pathlib import Path

_loaded = False


def project_root() -> Path:
    """Directory containing pyproject.toml and the outreach package."""
    pkg = Path(__file__).resolve().parent
    candidate = pkg.parent
    if (candidate / "pyproject.toml").exists() and (candidate / "outreach").is_dir():
        return candidate
    cwd = Path.cwd().resolve()
    for d in [cwd, *cwd.parents]:
        if (d / "pyproject.toml").exists() and (d / "outreach").is_dir():
            return d
    return candidate


def load_environment() -> Path:
    """Load .env from project root, then optional .env in cwd. Safe to call many times.

    Uses override=True so values from .env replace empty shell variables (a common issue:
    `export GROQ_API_KEY=` in a profile blocks dotenv otherwise).
    """
    global _loaded
    from dotenv import load_dotenv

    root = project_root()
    env_in_root = root / ".env"
    if env_in_root.is_file():
        load_dotenv(env_in_root, override=True)
    env_in_cwd = Path.cwd() / ".env"
    if env_in_cwd.is_file() and env_in_cwd.resolve() != env_in_root.resolve():
        load_dotenv(env_in_cwd, override=True)
    _loaded = True
    return root


def groq_key_missing_message() -> str:
    root = project_root()
    env_file = root / ".env"
    example = root / ".env.example"
    ex_hint = f" Copy {example.name} to {env_file.name} and edit." if example.exists() else ""

    diag = ""
    if not env_file.is_file():
        diag = f" There is no file at {env_file} yet."
    else:
        try:
            text = env_file.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            diag = f" Could not read {env_file}: {e}"
        else:
            found_line = False
            for line in text.splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("GROQ_API_KEY"):
                    found_line = True
                    _, _, rest = s.partition("=")
                    val = rest.strip().strip('"').strip("'")
                    if not val:
                        diag = (
                            f" {env_file} has GROQ_API_KEY but the value is empty. "
                            "Use: GROQ_API_KEY=gsk_your_actual_key (no spaces around =)."
                        )
                    break
            if not found_line and not diag:
                diag = f" {env_file} exists but has no GROQ_API_KEY= line."

    return (
        f"GROQ_API_KEY is not set.{ex_hint}{diag} "
        f"Expected file: {env_file} with one line like GROQ_API_KEY=gsk_... "
        "Or export a non-empty GROQ_API_KEY in the shell, then restart the server. "
        "Create a key at https://console.groq.com"
    )
