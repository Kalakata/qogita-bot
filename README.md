# Qogita MOV & Price Drop Bot

A bot that monitors Qogita cart allocations and watchlist prices, sending notifications to Microsoft Teams.

## What It Does

**Every 1 minute — MOV Check:**
- Checks all cart allocations for MOV (Minimum Order Value) progress
- When a cart reaches its MOV, sends a Teams notification with a full cart summary
- Tracks notified carts to avoid duplicates

**Every hour — Price Drop Report:**
- Fetches all watchlist items priced below target
- Sends a Teams card with the top 10 deals (sorted by biggest discount)
- Uploads the full deal list as a CSV to a GitHub Gist with a link in the card
- GTINs are clickable links to the Qogita product page

## Setup

### Prerequisites

- Python 3.11+
- GitHub account
- Microsoft Teams with a Microsoft 365 subscription
- Qogita account (qogita.com)

### 1. Clone and install

```bash
git clone git@github.com:Kalakata/qogita-bot.git
cd qogita-bot
pip install -r requirements.txt
```

### 2. Create a Teams Workflow webhook

1. Open Microsoft Teams
2. Go to **Apps** → search for **Workflows**
3. Click **Create** → search for **"Send webhook alerts to a channel"**
4. Select your Team and Channel
5. Save — copy the webhook URL (must include `&sig=` parameter)

### 3. Set GitHub repository secrets

```bash
gh secret set QOGITA_EMAIL      # Your qogita.com email
gh secret set QOGITA_PASSWORD    # Your qogita.com password
gh secret set TEAMS_WEBHOOK_URL  # The webhook URL from step 2
```

### 4. Set up cron-job.org (for reliable 1-minute triggering)

GitHub Actions cron is unreliable for short intervals, so we use cron-job.org to trigger the workflow.

1. Create a fine-grained GitHub PAT at https://github.com/settings/tokens?type=beta
   - Repository access: Only `qogita-bot`
   - Permissions: Actions → Read and Write
2. Sign up at https://cron-job.org (free)
3. Create a new cron job:
   - **URL:** `https://api.github.com/repos/Kalakata/qogita-bot/actions/workflows/check-mov.yml/dispatches`
   - **Schedule:** Every 1 minute
   - **Method:** POST
   - **Headers:**
     - `Authorization` → `Bearer <your-github-pat>`
     - `Accept` → `application/vnd.github+json`
     - `Content-Type` → `application/json`
   - **Body:** `{"ref":"master"}`
4. Save and enable

### 5. Run locally (optional, for testing)

```bash
cp .env.example .env
# Edit .env with your credentials

QOGITA_EMAIL=... QOGITA_PASSWORD=... TEAMS_WEBHOOK_URL=... python main.py
```

## How It Works

```
cron-job.org (every 1 min)
    → triggers GitHub Actions workflow
        → runs main.py
            → authenticates with Qogita API
            → checks cart allocations (MOV)
            → every 60th run: checks watchlist prices
            → sends Teams notifications via webhook
            → commits state.json back to repo
```

## State Management

`state.json` tracks:
- `cart_qid` — current active cart (resets when cart changes)
- `notified` — list of cart FIDs already notified for MOV
- `run_count` — increments each run, price check triggers on every 60th

## Project Structure

```
qogita-bot/
├── .github/workflows/check-mov.yml  — GitHub Actions workflow
├── main.py                          — Entry point and orchestration
├── qogita_client.py                 — Qogita API wrapper
├── teams_notifier.py                — Teams Adaptive Card notifications
├── state.py                         — State persistence (JSON)
├── state.json                       — Notification state
├── tests/                           — Test suite
├── requirements.txt                 — Python dependencies
└── .env.example                     — Environment variable template
```

## Cost

- **cron-job.org:** Free
- **GitHub Actions:** Free (2,000 min/month for private repos)
- **Teams webhook:** Included with Microsoft 365
