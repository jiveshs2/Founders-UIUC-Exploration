#!/usr/bin/env python3
"""Fill empty keys in .env using values from .env.save (same folder as pyproject.toml).

Run from repo root:
  python3 scripts/merge_env_from_save.py

Use after accidentally running `cp .env.example .env` if you still have a backup
like `.env.save` with real values.
"""

from __future__ import annotations

from pathlib import Path


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        if not k:
            continue
        out[k] = v.strip().strip('"').strip("'")
    return out


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    save_path = root / ".env.save"
    if not env_path.is_file():
        raise SystemExit(f"Missing {env_path}")
    if not save_path.is_file():
        raise SystemExit(f"Missing {save_path} — nothing to merge from.")

    save = _parse_env(save_path)
    lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
    filled: list[str] = []
    out_lines: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            out_lines.append(line)
            continue
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip()
        if k and not v and k in save and save[k]:
            out_lines.append(f"{k}={save[k]}")
            filled.append(k)
        else:
            out_lines.append(line)

    env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    if filled:
        print("Merged into .env:", ", ".join(filled))
    else:
        print("No empty keys matched values in .env.save (nothing to merge).")


if __name__ == "__main__":
    main()
