"""Create .env from .env.example if missing. Run: python -m outreach.ensure_env"""

from __future__ import annotations

import shutil
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def main() -> None:
    root = project_root()
    example = root / ".env.example"
    target = root / ".env"
    if target.is_file():
        print(f"Your config file already exists:\n  {target}\nOpen it in an editor and fill the lines after each = sign.")
        return
    if not example.is_file():
        raise SystemExit(f"Missing template: {example}")
    shutil.copyfile(example, target)
    print(
        f"Created:\n  {target}\n\n"
        "Next steps:\n"
        "  1. Open that file in TextEdit, Notepad, or VS Code.\n"
        "  2. Put your Groq key on the GROQ_API_KEY= line (right after the =).\n"
        "  3. Add any email-finder keys you use.\n"
        "  4. Save, then start the app again.\n\n"
        "See GETTING_STARTED.md in this folder for pictures-style instructions."
    )


if __name__ == "__main__":
    main()
