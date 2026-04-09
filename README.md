# Founders outreach tool

Pulls companies from a webpage, optionally finds emails via **Hunter** and **Snov** (free monthly quotas only — no paid email APIs), and drafts outreach with AI (**Groq** has a generous free tier; check their site for limits).

## Quick start (non-technical)

**Open the file [GETTING_STARTED.md](GETTING_STARTED.md)** in this folder and follow it step by step.

Summary:

1. Install once (Python virtual environment + packages — commands are in GETTING_STARTED).
2. Copy **`.env.example`** to **`.env`** and type your keys on the lines that end with `=`.
3. Run **`.venv/bin/outreach-web`** and open **http://127.0.0.1:8765**.

Create **`.env`** automatically if needed:

```bash
.venv/bin/python -m outreach.ensure_env
```

## What you edit where

| Where | What |
|--------|------|
| **`.env` file** | Keys for Groq, optional Hunter/Snov (free-tier email lookup), Outlook, etc. |
| **This web page** (after starting `outreach-web`) | Page link, who to include, your message — not keys |
| **`credentials.json`** | Only if you use **Google** Sheet + Doc export |

## Requirements

- Python 3.10+
- A **Groq** API key (free tier available)

## Compliance

Review every draft before sending. Respect website terms and each provider’s rules.
