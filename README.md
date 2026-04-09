# Founders Outreach Automation

Pulls companies from a webpage, finds contact emails, and drafts personalized outreach emails using AI. Built for [Founders at UIUC](https://founders.illinois.edu/).

---

## Setup (One Time)

### 1. Install Git (Windows only — Mac already has it)

**Windows:** Download and install Git from **https://git-scm.com**. Use all the default options in the installer.

**Mac:** Git is pre-installed. Nothing to do.

### 2. Install Python (skip if you already have it)

**Mac:** Open **Terminal** (Cmd + Space → type "Terminal") and run:
```
python3 --version
```
If you see a version number (3.10+), skip ahead. Otherwise, download Python from **https://www.python.org/downloads/** and install it.

**Windows:** Open **Command Prompt** (Windows key → type "cmd") and run:
```
python --version
```
If you see a version number (3.10+), skip ahead. Otherwise, download Python from **https://www.python.org/downloads/** — during install, **check "Add Python to PATH"**.

### 3. Clone the repo

Open Terminal (Mac) or Command Prompt (Windows) and run:

```
cd ~/Desktop
git clone https://github.com/jiveshs2/Founders-UIUC-Exploration.git
```

This creates a folder called `Founders-UIUC-Exploration` on your Desktop.

### 4. Install the app

Run these commands one at a time:

**Mac:**
```
cd ~/Desktop/Founders-UIUC-Exploration
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
.venv/bin/playwright install chromium
```

**Windows:**
```
cd %USERPROFILE%\Desktop\Founders-UIUC-Exploration
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .
.venv\Scripts\playwright install chromium
```

Each command may take a minute — wait for it to finish before running the next one.

### 5. Get your AI keys (free)

You need at least one. We recommend getting both so the app has a backup.

**Groq (primary):**
1. Go to **https://console.groq.com** and sign up
2. Click **API Keys** → **Create API Key**
3. Copy the key (starts with `gsk_`)

**Gemini (backup):**
1. Go to **https://aistudio.google.com/apikey** and sign in with Google
2. Click **Create API key**
3. Copy the key (starts with `AIza`)

### 6. Set up your config file

**Mac:**
```
cd ~/Desktop/Founders-UIUC-Exploration
cp .env.example .env
open -e .env
```

**Windows:**
```
cd %USERPROFILE%\Desktop\Founders-UIUC-Exploration
copy .env.example .env
notepad .env
```

This opens the config file in a text editor. Find these lines and paste your keys directly after the `=` with **no spaces**:

```
GROQ_API_KEY=gsk_paste_your_key_here
GEMINI_API_KEY=AIza_paste_your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Save and close the file.

---

## Running the App

**Mac:**
```
cd ~/Desktop/Founders-UIUC-Exploration
.venv/bin/outreach-web
```

**Windows:**
```
cd %USERPROFILE%\Desktop\Founders-UIUC-Exploration
.venv\Scripts\outreach-web
```

Then open your browser to: **http://127.0.0.1:8765**

To stop: press **Ctrl + C** in Terminal / Command Prompt.

---

## Using the App

| Field | What to enter |
|---|---|
| **Page URL** | Link to the page listing companies (e.g. a YC batch page) |
| **Which companies** | Describe which companies you want from that page |
| **Event description** | What you're inviting them to |
| **What's in it for them** | Why they'd want to attend |
| **Tone** | Pick an email tone from the dropdown |
| **Sign-off** | Your closing (e.g. "Best Regards, Your Name") |
| **Word limit** | Max words for the email body |
| **Limit companies** | Cap how many to process (use 1 while testing) |
| **Export mode** | Dry run (preview only), Outlook, or Google |

---

## Export Options

### Dry Run (no setup needed)
Preview emails on screen without saving anywhere. Use this for testing.

### Outlook Drafts
Creates drafts in your Outlook inbox.

1. Go to **https://portal.azure.com** → search **App registrations** → **New registration**
2. Name: anything (e.g. "Outreach Tool")
3. Supported account types: **"Accounts in any organizational directory and personal Microsoft accounts"**
4. Register, then copy the **Application (client) ID**
5. Go to **Authentication** → **Add a platform** → **Mobile and desktop** → check `http://localhost` → Save
6. Go to **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated** → add **Mail.ReadWrite** and **User.Read**
7. Open your `.env` file and add:
   ```
   OUTLOOK_CLIENT_ID=paste-your-client-id-here
   ```
8. Restart the app. First export will open a browser to sign in.

### Google Sheets + Docs
Creates a spreadsheet and document in your Google Drive.

1. Go to **https://console.cloud.google.com** → create a new project
2. Enable **Google Sheets API** and **Google Docs API** (find them under APIs & Services → Library)
3. Set up an **OAuth consent screen** (External is fine, add yourself as test user)
4. Go to **Credentials** → **Create Credentials** → **OAuth client ID** → type: **Desktop app**
5. Download the JSON file and rename it to **`credentials.json`**
6. Move `credentials.json` into the project folder (same folder as `.env`)
7. Restart the app. First export will open a browser to sign in.

---

## Optional: More Email Finder Keys

More keys = more emails found. All have free tiers.

| Service | Sign up | Add to `.env` |
|---|---|---|
| Hunter | https://hunter.io | `HUNTER_API_KEY=your_key` |
| Snov | https://snov.io | `SNOV_CLIENT_ID=your_id` and `SNOV_CLIENT_SECRET=your_secret` |
| Apollo | https://app.apollo.io | `APOLLO_API_KEY=your_key` |

Always restart the app after editing `.env`.

---

## Getting Updates

When the app is updated, open Terminal (Mac) or Command Prompt (Windows) and run:

```
cd ~/Desktop/Founders-UIUC-Exploration
git pull
```

That's it — you now have the latest version. If dependencies changed, also run:

**Mac:**
```
.venv/bin/pip install -r requirements.txt
```

**Windows:**
```
.venv\Scripts\pip install -r requirements.txt
```

Your `.env` file and keys are untouched — they stay on your machine.

---

## For Teams

Everyone follows this README on their own computer. Each person keeps their own `.env` and `credentials.json` — never share or commit these files.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "GROQ_API_KEY is not set" | Open `.env`, make sure the line reads `GROQ_API_KEY=your_key` with no spaces around `=`. Restart. |
| "No rows extracted" | Try a more specific URL, or re-run `playwright install chromium` from step 3. |
| Rate limit error (429) | Wait a few minutes and try again. Reduce "Limit companies" to 1. |
| "command not found" | Make sure you're in the project folder and using `.venv/bin/outreach-web` (Mac) or `.venv\Scripts\outreach-web` (Windows). |
| Outlook sign-in fails | Verify you selected the multi-tenant account type and added `http://localhost` as a redirect URI in Azure. |
| Google sign-in fails | Make sure `credentials.json` is in the project folder and both APIs are enabled. |

---

## Compliance

Review every draft before sending. Respect website terms and each email provider's acceptable use policies.
