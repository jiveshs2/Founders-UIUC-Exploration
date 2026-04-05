# Team setup guide

This document is for anyone cloning **[Founders-UIUC-Exploration](https://github.com/jiveshs2/Founders-UIUC-Exploration)** (or a copy of this repo) onto their own computer.

**Each teammate uses their own API keys and Google OAuth files.** Keys are stored only in local files that are **never** committed to Git (see [Security](#security-never-commit-these)).

---

## Prerequisites

- **macOS, Linux, or Windows** (examples below use macOS/Linux paths; on Windows use `\.venv\Scripts\` instead of `.venv/bin/` where applicable).
- **Python 3.10 or newer** — check with `python3 --version`.
- **Git** — check with `git --version`.
- Access to the GitHub repository (read is enough to clone).

---

## 1. Clone the repository

```bash
cd ~/Desktop   # or wherever you keep projects
git clone https://github.com/jiveshs2/Founders-UIUC-Exploration.git
cd Founders-UIUC-Exploration
```

If the project lives in a **subfolder** (e.g. the repo root contains `outreach-automation/`), `cd` into that folder for all remaining steps:

```bash
cd outreach-automation
```

You should see `pyproject.toml`, `requirements.txt`, and the `outreach/` package folder.

---

## 2. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

**If you move** this folder later (e.g. to another path), delete `.venv` and run the four lines again so scripts point at the correct location.

---

## 3. Create your personal `.env` file

The app reads secrets from a file named **`.env`** in the project root (same folder as `pyproject.toml`).

```bash
cp .env.example .env
```

Open **`.env`** in a text editor and **fill in your own keys** (see [Section 4](#4-obtain-your-own-api-keys)). Example shape:

```bash
GROQ_API_KEY=gsk_your_key_here
HUNTER_API_KEY=optional
SNOV_CLIENT_ID=optional
SNOV_CLIENT_SECRET=optional
APOLLO_API_KEY=optional
```

Rules:

- **One variable per line**, no spaces around `=`.
- **Do not commit** `.env` (it is in `.gitignore`).
- **Do not share** your `.env` in Slack/email; each person maintains their own.

After editing `.env`, **restart** the CLI or web server so changes load.

---

## 4. Obtain your own API keys

Everyone should create accounts under **their own email** (or org-approved accounts) and generate **personal** keys. That way quotas, billing, and access are clear per person.

### 4.1 Groq (required)

Used to interpret the web page and to draft outreach emails.

1. Go to **[console.groq.com](https://console.groq.com)** and sign in.
2. Open **API keys** → create a key.
3. Copy the key into `.env`:
   ```bash
   GROQ_API_KEY=gsk_...
   ```

### 4.2 Hunter.io (optional — email finder, first in chain)

1. Sign up at **[hunter.io](https://hunter.io)**.
2. Open API / dashboard and copy your API key.
3. In `.env`:
   ```bash
   HUNTER_API_KEY=...
   ```

### 4.3 Snov.io (optional — email finder, second in chain)

1. Sign up at **[snov.io](https://snov.io)**.
2. In account/API settings, create **Client ID** and **Client Secret**.
3. In `.env` (both are required for Snov to run):
   ```bash
   SNOV_CLIENT_ID=...
   SNOV_CLIENT_SECRET=...
   ```

### 4.4 Apollo.io (optional — email finder, third in chain)

May consume **paid credits** on your Apollo plan.

1. Use your Apollo workspace and **[API documentation](https://docs.apollo.io/)** to create or copy a **master API key**.
2. In `.env`:
   ```bash
   APOLLO_API_KEY=...
   ```

### How the email providers work together

If you configure more than one of Hunter, Snov, and Apollo, the tool tries them **in order**: Hunter → Snov → Apollo. If one hits a quota/rate limit or finds no email, the next provider runs. You can use **only Groq** (no email keys) if you only want drafts without automated email lookup.

---

## 5. Google Sheets and Google Docs (per person)

Exporting to a Sheet and Doc uses **OAuth**. Each developer should use **their own** `credentials.json` unless your team explicitly shares a single internal OAuth client (coordinate with your lead).

1. Go to **[Google Cloud Console](https://console.cloud.google.com)**.
2. Create or select a project.
3. Enable **Google Sheets API** and **Google Docs API**.
4. Configure the **OAuth consent screen** (Internal or External). If the app is in **Testing**, add your Google account under **Test users**.
5. **Credentials** → **Create credentials** → **OAuth client ID** → type **Desktop app** → download the JSON.
6. Save the file as **`credentials.json`** in the project root (same folder as `.env`). This file is **gitignored**.
7. Run the tool once; a browser window opens to sign in with Google. After that, **`token.json`** is created locally (also gitignored).

---

## 6. Run the tools

Make the helper scripts executable (once):

```bash
chmod +x ./outreach-run ./outreach-run-web
```

### Web UI (recommended to start)

```bash
./outreach-run-web
```

Open **http://127.0.0.1:8765** in your browser. Use **Dry run** first if you want to skip Google and only preview text on the page.

### CLI

```bash
./outreach-run run \
  --url "https://example.com/page" \
  --extract-prompt "Describe what to extract from the page." \
  --purpose-prompt "Why you are reaching out."
```

---

## 7. Staying up to date with the team

When someone pushes changes:

```bash
cd /path/to/Founders-UIUC-Exploration   # or outreach-automation
git pull
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

If `requirements.txt` changed, the `pip install` line updates your packages. Your **`.env` and `credentials.json` are yours** and are not overwritten by `git pull`.

---

## 8. Troubleshooting

| Problem | What to try |
|--------|-------------|
| `command not found: outreach` | Use `./outreach-run` or `.venv/bin/outreach` (the command is inside the venv). |
| `bad interpreter: .../python3.12: no such file` | You moved the folder; run `rm -rf .venv` and recreate the venv (section 2). |
| `GROQ_API_KEY is not set` | Ensure `.env` has a non-empty `GROQ_API_KEY=` line; save the file; restart the server. |
| Google errors on export | Check `credentials.json` path, APIs enabled, and that your Google account is a **test user** if the OAuth app is in testing mode. |

---

## Security: never commit these

Do **not** add or commit:

- `.env`
- `.env.save` or other backup env files
- `credentials.json`
- `token.json`

If you ever accidentally commit secrets, **rotate those keys immediately** in the provider dashboards and contact your team lead.

---

## Questions

For repo-specific workflow (branches, reviews), follow your team’s process. For how this app behaves, see **[README.md](README.md)**.
