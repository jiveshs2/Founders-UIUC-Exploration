# Getting started (simple)

Follow these steps **in order**. You only need a web browser and the **Terminal** app (Mac) or **Command Prompt** (Windows).

---

## Step 1 — Install the tool (one time)

1. Put the `outreach-automation` folder somewhere on your computer (for example **Desktop**).
2. Open **Terminal** (Mac) or **Command Prompt** (Windows).
3. Go into the folder (replace the path if yours is different):

```bash
cd ~/Desktop/outreach-automation
```

4. Run these four commands **one after the other**:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
.venv/bin/playwright install chromium
```

*(On Windows, use `.venv\Scripts\pip` instead of `.venv/bin/pip`.)*

---

## Step 2 — Create your `.env` file and add keys

The app reads secrets from a file named **`.env`** in the `outreach-automation` folder.

### Create the file

```bash
cd ~/Desktop/outreach-automation
cp .env.example .env
```

Or run either of these (same result):

```bash
.venv/bin/python -m outreach.ensure_env
```

```bash
.venv/bin/outreach-init-env
```

### Edit the file

Open **`.env`** in any text editor:

- Mac (TextEdit): `open -e .env`
- Simple terminal editor: `nano .env`

You will see lines like:

```text
GROQ_API_KEY=
HUNTER_API_KEY=
```

**Put your key on the same line, right after the `=` sign**, with **no spaces**:

```text
GROQ_API_KEY=gsk_your_real_key_from_groq
```

**Minimum to run:** fill **`GROQ_API_KEY`** (free at [console.groq.com](https://console.groq.com)) **or** **`GEMINI_API_KEY`** (free at [ai.google.dev](https://ai.google.dev)).

**To find more emails:** the app pulls addresses from the listing page HTML (when present), scrapes common paths on each company site (`/contact`, `/about`, …), then runs optional finder APIs you configure in `.env` (**Hunter**, **Snov**, **Apollo**, **Anymail Finder**, **Findymail**, **Skrapp**). For unknown addresses it can try common `first.last@domain` patterns **only if** you add a free verification key (**ZeroBounce** and/or **Abstract** email validation). See `.env.example` for names and toggles; check each vendor’s site for current free limits and acceptable use.

**Save** the file.

---

## Step 3 — Start the app

```bash
cd ~/Desktop/outreach-automation
.venv/bin/outreach-web
```

Open your browser to: **http://127.0.0.1:8765**

---

## Step 4 — Saving results (pick one)

| What you want | What to do |
|---------------|------------|
| **Preview only** | Check **Dry run** — no Outlook or Google needed. |
| **Google Sheet + Doc** | Add **`credentials.json`** to the project folder (Google Cloud “Desktop app” OAuth — see below). In the app, choose **Google**. |
| **Outlook drafts** | Add **`OUTLOOK_CLIENT_ID`** to `.env` (Azure app — see below). In the app, choose **Outlook**. |

If you choose **Outlook** but only set up **Google**, the app will **automatically use Google** when it finds `credentials.json`.

If you have **neither** Outlook nor Google set up, use **Dry run** or the app will show a short message telling you what to add.

---

## Google `credentials.json` (for Sheet + Doc)

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project → enable **Google Sheets API** and **Google Docs API**.
3. **OAuth consent screen** → add yourself as a test user if asked.
4. **Credentials** → **Create** → **OAuth client ID** → type **Desktop** → download JSON.
5. Rename/move the file to **`credentials.json`** inside **`outreach-automation`** (same folder as `.env`).

The first run opens a browser once to sign in; then **`token.json`** appears automatically.

---

## Outlook `OUTLOOK_CLIENT_ID` (optional)

1. Go to [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations** → **New registration**.
2. **Authentication** → add platform **Mobile and desktop** → enable **`http://localhost`**.
3. **API permissions** → **Microsoft Graph** → delegated **Mail.ReadWrite** and **User.Read**.
4. Copy **Application (client) ID** into `.env`:

```text
OUTLOOK_CLIENT_ID=paste-the-client-id-here
```

First real export opens a browser to sign in to Microsoft.

---

## If something goes wrong

| Problem | Try this |
|--------|----------|
| “GROQ_API_KEY is not set” | Open `.env` — the line must be `GROQ_API_KEY=something` with no space around `=`. Restart the server. |
| “No rows extracted” | Use a page that actually lists companies; try a smaller URL (one batch). |
| YC page looks empty | Run `playwright install chromium` again from Step 1. |
| Google error | Check `credentials.json` is in the right folder and APIs are enabled. |
| Command not found | Always use `.venv/bin/outreach-web` from inside `outreach-automation`. |

---

## Restoring keys after a mistake

If you ran `cp .env.example .env` and wiped your file, keep a backup as **`.env.save`** and run:

```bash
python3 scripts/merge_env_from_save.py
```

---

That’s it — fill **`.env`**, start **`outreach-web`**, use the browser form for the **page URL** and **what to say**, not for API keys.
