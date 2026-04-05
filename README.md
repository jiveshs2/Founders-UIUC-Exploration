# Outreach automation

CLI pipeline: fetch a web page, use Groq to extract structured rows from your instructions, optionally find company emails via Hunter.io, generate draft outreach with Groq, then write a **Google Sheet** and **Google Doc** for review.

**Teammates:** start with **[TEAM_SETUP.md](TEAM_SETUP.md)** (clone from Git, install, create your own API keys and Google OAuth files).

## Setup

1. Create a Python 3.10+ virtual environment and install dependencies:

   ```bash
   cd outreach-automation
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/pip install -e .
   ```

   After you move this folder to a new machine or path, recreate the venv (or run `pip install -e .` again inside the existing venv) so editable installs and console scripts point at the right directory.

2. Add API keys — see **[API keys](#api-keys)** below.

3. **Google Cloud**
   - Create a project, enable **Google Sheets API** and **Google Docs API**.
   - OAuth consent screen: add yourself as test user if in testing mode.
   - Create **OAuth client ID** (Desktop app), download JSON, save as `credentials.json` in this directory (gitignored).

4. Run (pick one). Typing bare `outreach` fails with **command not found** unless `.venv/bin` is on your `PATH` (e.g. after `source .venv/bin/activate`). The console script is always at `.venv/bin/outreach`.

   The repo includes **`outreach-run`** because the Python package already uses the `outreach/` folder name, so we avoid a conflicting root-level `outreach` file.

   ```bash
   chmod +x ./outreach-run
   ./outreach-run run \
     --url "https://www.ycombinator.com/companies" \
     --extract-prompt "List only companies from the Winter 2026 batch. For each: founder names, company name, batch, company website URL." \
     --purpose-prompt "Invite founders to a small founder dinner in SF next month."
   ```

   Equivalent:

   ```bash
   .venv/bin/outreach run --url "..." --extract-prompt "..." --purpose-prompt "..."
   # or
   .venv/bin/python -m outreach.cli run --url "..." --extract-prompt "..." --purpose-prompt "..."
   ```

   The word `run` is optional; you can omit it and pass `--url` first.

   First run opens a browser to authorize Google; `token.json` is saved for later runs.

## Web UI (local)

A simple form exposes the same inputs as the CLI. It only listens on **127.0.0.1** (your machine). Do not expose this port to the internet without adding authentication.

```bash
chmod +x ./outreach-run-web
./outreach-run-web
# or: .venv/bin/outreach-web
# or: .venv/bin/python -m uvicorn outreach.web:app --host 127.0.0.1 --port 8765
```

Open **http://127.0.0.1:8765** in your browser. Use **Dry run** first if you want to skip Google and only preview drafts on the page. The web UI does **not** ask for keys in the browser; it reads the same `.env` file as the CLI.

## API keys

### What you need

| Key / file | Required? | What it’s for |
|------------|-----------|----------------|
| **`GROQ_API_KEY`** | **Yes** | Groq LLM: extract rows from the page + write each outreach email. |
| **`HUNTER_API_KEY`** | No | Hunter.io: find emails by company domain (first in the email chain). |
| **`SNOV_CLIENT_ID`** + **`SNOV_CLIENT_SECRET`** | No | Snov.io: both must be set for Snov to run (second in the chain). |
| **`APOLLO_API_KEY`** | No | Apollo.io: people match + reveal email (third in the chain; may use paid credits). |
| **`credentials.json`** | Only for Google export | Not inside `.env` — a JSON file from Google Cloud (Desktop OAuth client). See [Setup](#setup) step 3. |

You can enable **any combination** of Hunter, Snov, and Apollo. If one runs out of quota or finds nothing, the next configured provider is used.

### How to add them (`.env` file)

1. In the **`outreach-automation`** folder (next to `pyproject.toml`), create `.env` if it doesn’t exist:

   ```bash
   cd /path/to/outreach-automation
   cp .env.example .env
   ```

2. Open `.env` in any text editor (Terminal example):

   ```bash
   nano .env
   ```

3. For each key, add **one line per variable**, **no spaces around `=`**, and **no quotes** unless your key itself contains spaces (rare):

   ```bash
   GROQ_API_KEY=gsk_your_actual_key_here
   HUNTER_API_KEY=your_hunter_key_here
   SNOV_CLIENT_ID=your_snov_client_id
   SNOV_CLIENT_SECRET=your_snov_client_secret
   APOLLO_API_KEY=your_apollo_master_key
   ```

4. Save the file, then **restart** the CLI or web server so new values load.

5. **Never commit `.env`** — it is listed in `.gitignore`. Don’t paste keys into the web form or chat.

### Where to get each key

- **Groq** — [console.groq.com](https://console.groq.com) → API keys → create key → copy into `GROQ_API_KEY=...`.
- **Hunter** — [hunter.io](https://hunter.io) → sign up / API → copy API key into `HUNTER_API_KEY=...`.
- **Snov** — [snov.io](https://snov.io) → account / API settings → create **Client ID** and **Client Secret** → put them in `SNOV_CLIENT_ID` and `SNOV_CLIENT_SECRET` (both required).
- **Apollo** — [Apollo API / settings](https://docs.apollo.io/) → create or copy a **master API key** → `APOLLO_API_KEY=...`.

### Optional: export in the shell instead

Instead of `.env`, you can set variables for that terminal session only:

```bash
export GROQ_API_KEY='gsk_...'
export HUNTER_API_KEY='...'
```

Then run `./outreach-run` or `./outreach-run-web` from **that same terminal window**. For a permanent setup, `.env` is usually easier.

## Compliance

Respect site terms of use and robots rules. Use email finder APIs within their terms. Review all drafts before sending; this tool does not send mail.

## Environment variables (quick reference)

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key |
| `HUNTER_API_KEY` | No | Hunter.io domain search |
| `SNOV_CLIENT_ID` | No* | Snov.io client ID (*both ID + secret needed for Snov) |
| `SNOV_CLIENT_SECRET` | No* | Snov.io client secret |
| `APOLLO_API_KEY` | No | Apollo `people/bulk_match` + reveal emails (uses credits) |
| `GROQ_MODEL` | No | Defaults to `llama-3.3-70b-versatile` |
