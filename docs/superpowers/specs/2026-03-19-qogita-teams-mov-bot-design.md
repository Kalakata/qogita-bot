# Qogita Teams MOV Notification Bot — Design Spec

## Overview

A Python script triggered by a GitHub Actions scheduled workflow that polls the Qogita Buyer API for cart allocation MOV (Minimum Order Value) progress and sends one-way notifications to a Microsoft Teams channel via an incoming webhook when any allocation reaches its MOV threshold.

## Problem

Monitoring cart allocations on Qogita requires manually checking the platform. The team needs automatic notifications when a supplier allocation in a cart reaches its MOV so they can act on it promptly.

## Solution

A lightweight Python script run by GitHub Actions on a cron schedule that:

1. Authenticates with the Qogita API
2. Fetches all allocations for the active cart
3. Detects allocations where `movProgress >= 1.0`
4. Sends a Teams notification for newly reached allocations
5. Tracks notified allocations via a `state.json` file committed back to the repo

## Architecture

```
┌──────────────────┐  poll every 15 min  ┌──────────────┐
│ GitHub Actions    │ ────────────────── │ Qogita API   │
│ (scheduled wf)   │ ◄───────────────── │              │
│                   │  allocation data   │              │
│                   │                    └──────────────┘
│                   │
│                   │  POST webhook      ┌─────────────────┐
│                   │ ────────────────── │ Teams Channel   │
│                   │                    └─────────────────┘
│                   │
│                   │  git commit/push   ┌─────────────────┐
│                   │ ────────────────── │ state.json      │
└───────────────────┘                    │ (in repo)       │
                                         └─────────────────┘
```

## API Details

### Authentication

- **Endpoint:** `POST /auth/login/`
- **Body:** `{"email": "...", "password": "..."}`
- **Returns:** `accessToken` and `user.activeCartQid`

### Cart Allocations

- **Endpoint:** `GET /carts/{cart_qid}/allocations/?page={n}&size=50`
- **Paginated:** Follow `next` field until no more results
- **Key fields per allocation:**
  - `fid` — supplier identifier (e.g., "577MOO")
  - `movProgress` — decimal string, "0.000" to "1.000+" (1.0 = MOV reached)
  - `mov` — MOV threshold amount (e.g., "2800.00")
  - `movCurrency` — currency code (e.g., "EUR")
  - `subtotal` — current cart value for this supplier

### MOV Detection Logic

```python
reached = [a for a in allocations if float(a["movProgress"]) >= 1.0]
```

## Components

### `qogita_client.py` — Qogita API wrapper

- `authenticate(email, password) -> str` — returns access token
- `get_active_cart_qid(email, password) -> tuple[str, str]` — returns (token, cart_qid)
- `get_allocations(token, cart_qid) -> list[dict]` — paginates through all allocations, returns list of allocation summaries

### `teams_notifier.py` — Teams webhook sender

- `send_notification(webhook_url, allocation) -> None` — POSTs a message card to the Teams webhook
- Message format: "Cart allocation {fid} has reached its MOV! ({currency} {mov})"

### `main.py` — Entry point

1. Load config from environment variables
2. Read `state.json` for previously notified allocations
3. Authenticate with Qogita API
4. Fetch all allocations for the active cart
5. Filter for `movProgress >= 1.0`
6. For each newly reached allocation (not in state), send Teams notification
7. Update `state.json` with newly notified allocations
8. Commit and push `state.json` if changed

### State Tracking — `state.json` (git-based)

- **File:** `state.json` in repo root
- **Contents:** JSON object mapping cart QID to a list of notified allocation FIDs
- Prevents duplicate notifications across workflow runs
- State resets naturally when a new cart is created (new cart QID = fresh entry)
- Example:
  ```json
  {
    "cart_qid": "c722c553-0ceb-4d76-9ad4-a32641505b74",
    "notified": ["577MOO", "MR4LK9"]
  }
  ```

## Configuration

Stored as GitHub repository secrets:

| Secret | Description |
|--------|-------------|
| `QOGITA_EMAIL` | Qogita account email |
| `QOGITA_PASSWORD` | Qogita account password |
| `TEAMS_WEBHOOK_URL` | Microsoft Teams incoming webhook URL |

## File Structure

```
qogita-bot/
├── .github/
│   └── workflows/
│       └── check-mov.yml    # Scheduled GitHub Actions workflow
├── main.py                  # Entry point
├── qogita_client.py         # Qogita API wrapper
├── teams_notifier.py        # Teams webhook sender
├── state.json               # Persisted notification state
├── requirements.txt         # requests
├── .env.example             # Template for local dev
└── .gitignore
```

## Deployment

- **Platform:** GitHub Actions (scheduled workflow)
- **Schedule:** `*/15 * * * *` (every 15 minutes — fits free tier for private repos)
- **Runtime:** Python 3.11+
- **State:** `state.json` committed back to repo after each run
- **Dependencies:** `requests`
- **Free tier usage:** ~2,880 runs/month x ~30s = ~1,440 minutes (within 2,000 min free tier for private repos)

## GitHub Actions Workflow

The workflow (`.github/workflows/check-mov.yml`):
1. Triggers on `schedule: cron "*/15 * * * *"`
2. Checks out the repo
3. Sets up Python 3.11
4. Installs dependencies from `requirements.txt`
5. Runs `main.py` with secrets as environment variables
6. If `state.json` changed, commits and pushes it back

The workflow needs `contents: write` permission to push state changes.

## Teams Webhook Setup

1. Create a Teams channel for notifications (e.g., "Qogita MOV Alerts")
2. Add an "Incoming Webhook" connector to the channel
3. Name it (e.g., "Qogita Bot") and copy the webhook URL
4. Add the URL as a repository secret named `TEAMS_WEBHOOK_URL`

## Error Handling

- Authentication failure: log error, exit with non-zero code (workflow shows as failed)
- API rate limit (429): log warning, exit (workflow retries next run)
- Teams webhook failure: log error, do not mark allocation as notified (will retry next run)
- Git push conflict: workflow uses `pull --rebase` before pushing to handle concurrent runs

## Testing

- Unit tests for MOV detection logic (filtering allocations by movProgress)
- Unit tests for notification deduplication logic
- Integration test against live Qogita API (manual, using existing credentials)
