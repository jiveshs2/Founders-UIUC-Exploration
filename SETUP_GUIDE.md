# Founders Outreach Automation — Setup Guide

This guide walks you through setting up the outreach tool from scratch. No coding experience required. Follow every step in order.

---

## What You Need Before Starting

- A computer (Mac or Windows)
- An internet connection
- About 15–20 minutes

---

## Part 1: Download the Code to Your Computer

1. Open your web browser and go to:
   **https://github.com/jiveshs2/Founders-UIUC-Exploration**

2. Click the green **"Code"** button near the top right.

3. Click **"Download ZIP"**.

4. Find the downloaded ZIP file (usually in your **Downloads** folder) and double-click it to unzip.

5. You should now have a folder called something like `Founders-UIUC-Exploration-main`. Rename it to **`outreach-automation`** for simplicity.

6. Move the **`outreach-automation`** folder to your **Desktop** (or anywhere you'll remember).

---

## Part 2: Install Python (if you don't already have it)

### Mac

1. Open the **Terminal** app. You can find it by pressing **Cmd + Space**, typing **Terminal**, and pressing Enter.

2. Type this and press Enter:
   ```
   python3 --version
   ```

3. If you see a version number (like `Python 3.12.0`), you're good — skip to Part 3.

4. If you see an error, install Python by going to **https://www.python.org/downloads/** and downloading the latest version. Run the installer and follow the prompts.

### Windows

1. Open **Command Prompt**. Press the **Windows key**, type **cmd**, and press Enter.

2. Type this and press Enter:
   ```
   python --version
   ```

3. If you see a version number (3.10 or higher), skip to Part 3.

4. If not, go to **https://www.python.org/downloads/** and download the latest version. When installing, **check the box that says "Add Python to PATH"** — this is important.

---

## Part 3: Install the App

### Mac

Open **Terminal** and type these commands one at a time, pressing Enter after each:

```
cd ~/Desktop/outreach-automation
```

```
python3 -m venv .venv
```

```
.venv/bin/pip install -r requirements.txt
```

```
.venv/bin/pip install -e .
```

```
.venv/bin/playwright install chromium
```

Wait for each command to finish before typing the next one. Some may take a minute or two — that's normal.

### Windows

Open **Command Prompt** and type these commands one at a time:

```
cd %USERPROFILE%\Desktop\outreach-automation
```

```
python -m venv .venv
```

```
.venv\Scripts\pip install -r requirements.txt
```

```
.venv\Scripts\pip install -e .
```

```
.venv\Scripts\playwright install chromium
```

---

## Part 4: Get Your API Keys (Free)

The app uses AI services to read web pages and write emails. You need at least one of these two keys. Both are free.

### Option A: Groq Key (recommended)

1. Go to **https://console.groq.com** in your browser.
2. Sign up for a free account (you can use Google sign-in).
3. Once logged in, click **"API Keys"** in the left sidebar.
4. Click **"Create API Key"**.
5. Give it any name (like "outreach") and click **Create**.
6. **Copy the key** — it starts with `gsk_`. Save it somewhere temporarily (you'll paste it in the next step).

### Option B: Gemini Key (backup / fallback)

1. Go to **https://aistudio.google.com/apikey** in your browser.
2. Sign in with your Google account.
3. Click **"Create API key"**.
4. **Copy the key** — it starts with `AIza`. Save it somewhere temporarily.

> We recommend getting **both** keys. The app uses Groq as the main AI and Gemini as a backup when Groq is busy.

---

## Part 5: Set Up Your Configuration File

The app reads your keys from a file called `.env`. Here's how to create it:

### Mac

In Terminal, make sure you're in the project folder, then run:

```
cd ~/Desktop/outreach-automation
cp .env.example .env
open -e .env
```

This opens the file in TextEdit.

### Windows

In Command Prompt:

```
cd %USERPROFILE%\Desktop\outreach-automation
copy .env.example .env
notepad .env
```

This opens the file in Notepad.

### What to Edit

You'll see a file with lines like:

```
GROQ_API_KEY=
GEMINI_API_KEY=
```

Paste your keys **directly after the `=` sign** with **no spaces**. For example:

```
GROQ_API_KEY=gsk_abc123yourActualKeyHere
GEMINI_API_KEY=AIzaSyYourActualKeyHere
GEMINI_MODEL=gemini-2.5-flash
```

> **Important:** The `GEMINI_MODEL=gemini-2.5-flash` line must be added or uncommented if you're using Gemini. This tells the app which AI model to use.

**Save the file** and close the editor.

---

## Part 6: Start the App

### Mac

```
cd ~/Desktop/outreach-automation
.venv/bin/outreach-web
```

### Windows

```
cd %USERPROFILE%\Desktop\outreach-automation
.venv\Scripts\outreach-web
```

You should see a message like:

```
INFO:     Uvicorn running on http://127.0.0.1:8765
```

**Open your browser** and go to: **http://127.0.0.1:8765**

You should see the Founders Outreach form. That's it — the app is running!

> **To stop the app:** go back to Terminal/Command Prompt and press **Ctrl + C**.
>
> **To restart it later:** repeat the two commands in this step.

---

## Part 7: Using the App

1. **Page URL** — Paste the link to the page listing companies (e.g., a YC batch page or a single company page like `https://www.ycombinator.com/companies/coasts`).

2. **Which companies to include** — Describe which companies from that page you want (e.g., "All companies" or "Only EdTech companies").

3. **Event description** — What you're inviting them to (e.g., "Illinois Founders EdTech Hackathon — a 36-hour build sprint").

4. **What's in it for them** — Why they'd want to come (e.g., "Opportunity to recruit UIUC engineers").

5. **Tone** — Pick one or more email tones from the dropdown.

6. **Sign-off** — Your closing (e.g., "Best Regards, Your Name").

7. **Word limit** — Maximum words for the email body (e.g., 120).

8. **Limit companies** — Cap how many companies to process (use 1 while testing).

9. **Export mode:**
   - **Dry run** — Preview emails without sending anything. Great for testing.
   - **Outlook** — Creates drafts in your Outlook inbox (requires setup below).
   - **Google** — Creates a Google Sheet + Doc (requires setup below).

10. Click **Run** and wait. Progress updates appear in the log area.

---

## Part 8: Saving Results (Optional — Pick One)

### Option 1: Dry Run (no setup needed)

Check the **Dry run** box in the app. Emails are previewed on screen but not saved anywhere. Perfect for testing.

### Option 2: Outlook Drafts

This creates email drafts directly in your Outlook inbox.

1. Go to **https://portal.azure.com** and sign in with your Microsoft account.
2. Search for **"App registrations"** in the top search bar and click it.
3. Click **"New registration"**.
4. Name it anything (e.g., "Outreach Automation").
5. Under **Supported account types**, select **"Accounts in any organizational directory and personal Microsoft accounts"**.
6. Click **Register**.
7. On the app's overview page, copy the **Application (client) ID**.
8. Click **"Authentication"** in the left sidebar.
9. Click **"Add a platform"** → choose **"Mobile and desktop applications"**.
10. Check the box for **`http://localhost`** and click **Configure**.
11. Click **"API permissions"** in the left sidebar.
12. Click **"Add a permission"** → **Microsoft Graph** → **Delegated permissions**.
13. Search for and add: **Mail.ReadWrite** and **User.Read**.
14. Click **"Grant admin consent"** (if available).
15. Open your `.env` file and paste the client ID:

```
OUTLOOK_CLIENT_ID=paste-your-client-id-here
```

16. Save `.env` and restart the app. The first time you export to Outlook, a browser window will open asking you to sign in to Microsoft.

### Option 3: Google Sheets + Docs

1. Go to **https://console.cloud.google.com**.
2. Create a new project (any name).
3. In the left sidebar, go to **APIs & Services** → **Library**.
4. Search for and enable **Google Sheets API**.
5. Search for and enable **Google Docs API**.
6. Go to **APIs & Services** → **OAuth consent screen**. Set it up (External is fine), add yourself as a test user.
7. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**.
8. Application type: **Desktop app**. Click Create.
9. Click **Download JSON**.
10. Rename the downloaded file to **`credentials.json`**.
11. Move it into your **`outreach-automation`** folder (same folder as `.env`).
12. Restart the app. The first time you export to Google, a browser window will open asking you to sign in.

---

## Part 9: Adding Email Finder API Keys (Optional, but Recommended)

The app tries to find email addresses for each company. More API keys = more emails found. All have free tiers.

| Service | Sign-up Link | What to Add in `.env` |
|---|---|---|
| Hunter.io | https://hunter.io/users/sign_up | `HUNTER_API_KEY=your_key` |
| Snov.io | https://snov.io | `SNOV_CLIENT_ID=your_id` and `SNOV_CLIENT_SECRET=your_secret` |
| Apollo.io | https://app.apollo.io/#/signup | `APOLLO_API_KEY=your_key` |

After adding any keys, **save `.env`** and **restart the app**.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **"GROQ_API_KEY is not set"** | Open `.env` and make sure the line reads `GROQ_API_KEY=your_key` with no spaces around `=`. Restart the app. |
| **"No rows extracted"** | The page might load with JavaScript. Make sure you ran `playwright install chromium` in Part 3. Also try a more specific URL. |
| **Rate limit error (429)** | You've hit the free tier limit. Wait a few minutes and try again, or reduce "Limit companies" to 1. |
| **"command not found"** | Make sure you're in the `outreach-automation` folder and using `.venv/bin/outreach-web` (Mac) or `.venv\Scripts\outreach-web` (Windows). |
| **App won't start** | Try running `cd ~/Desktop/outreach-automation && .venv/bin/python -m outreach.web` instead. |
| **Outlook sign-in fails** | Double-check that you selected "Accounts in any organizational directory and personal Microsoft accounts" in Azure. Also ensure `http://localhost` is added as a redirect URI. |
| **Google sign-in fails** | Make sure `credentials.json` is in the `outreach-automation` folder and both Sheets and Docs APIs are enabled. |
| **Wrong email found** | The app prioritizes founder-matching emails. If the founder name wasn't on the source page, it may pick a generic address. Try a YC company detail page (e.g., `https://www.ycombinator.com/companies/company-name`) for best results. |

---

## Quick Reference: Starting the App Each Time

Every time you want to use the app:

### Mac
```
cd ~/Desktop/outreach-automation
.venv/bin/outreach-web
```

### Windows
```
cd %USERPROFILE%\Desktop\outreach-automation
.venv\Scripts\outreach-web
```

Then open **http://127.0.0.1:8765** in your browser.

To stop: press **Ctrl + C** in Terminal / Command Prompt.

---

## Quick Reference: Editing `.env`

### Mac
```
cd ~/Desktop/outreach-automation
open -e .env
```

### Windows
```
cd %USERPROFILE%\Desktop\outreach-automation
notepad .env
```

Always restart the app after changing `.env`.
