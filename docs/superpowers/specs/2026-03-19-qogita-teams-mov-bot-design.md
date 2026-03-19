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

- **Base URL:** `https://api.qogita.com`

### Authentication

- **Endpoint:** `POST /auth/login/`
- **Body:** `{"email": "...", "password": "..."}`
- **Returns:** `accessToken` and `user.activeCartQid`
- Token is short-lived but sufficient for a single run (~30s). No refresh needed.

### Cart Allocations

- **Endpoint:** `GET /carts/{cart_qid}/allocations/?page={n}&size=50`
- **Pagination:** The response contains a `next` field. If `next` is not null, increment the page number and fetch again. If `next` is null or the `results` list is empty, stop.
- **Key fields per allocation:**
  - `fid` — supplier identifier string (e.g., "577MOO")
  - `movProgress` — decimal returned as a string (e.g., "0.922"). Converted to float for comparison. `>= 1.0` means MOV is reached.
  - `mov` — MOV threshold amount as string (e.g., "2800.00")
  - `movCurrency` — currency code (e.g., "EUR")
  - `subtotal` — current cart value for this supplier as string

### MOV Detection Logic

```python
reached = [a for a in allocations if float(a["movProgress"]) >= 1.0]
```

## Components

### `qogita_client.py` — Qogita API wrapper

- **Base URL:** `https://api.qogita.com`
- `login(email, password) -> tuple[str, str | None]` — authenticates and returns `(token, active_cart_qid)`. `active_cart_qid` may be `None` if no active cart exists.
- `get_allocations(token, cart_qid) -> list[dict]` — paginates through all allocations by incrementing the `page` parameter until `results` is empty. Returns a list of dicts with keys: `fid`, `movProgress`, `mov`, `movCurrency`, `subtotal`.

### `teams_notifier.py` — Teams webhook sender

- `send_notification(webhook_url, allocation) -> None` — POSTs a simple MessageCard JSON payload to the Teams webhook.
- Message format: `"Cart allocation {fid} has reached its MOV! ({movCurrency} {mov})"`

### `main.py` — Entry point

1. Load config from environment variables (`QOGITA_EMAIL`, `QOGITA_PASSWORD`, `TEAMS_WEBHOOK_URL`)
2. Read `state.json` (if missing or malformed, start with empty state)
3. Call `login()` — if `active_cart_qid` is `None`, log "no active cart" and exit cleanly (exit code 0)
4. If `cart_qid` in state differs from current `active_cart_qid`, reset state (old cart's notifications are irrelevant)
5. Fetch all allocations for the active cart
6. Filter for `movProgress >= 1.0`
7. For each newly reached allocation (FID not in `state.notified`), send Teams notification
8. Update `state.json` with current `cart_qid` and updated `notified` list
9. Write `state.json` to disk (the workflow handles git commit/push)

### State Tracking — `state.json` (git-based)

- **File:** `state.json` in repo root
- **Schema:**
  ```json
  {
    "cart_qid": "c722c553-0ceb-4d76-9ad4-a32641505b74",
    "notified": ["577MOO", "MR4LK9"]
  }
  ```
- **Initial state:** `{}` (empty object). First run handles this gracefully.
- **Cart transition:** When `active_cart_qid` changes, the state is fully replaced. Old cart data is not preserved (not needed).
- Prevents duplicate notifications across workflow runs.
- Race conditions are prevented by the workflow's `concurrency` setting (see below).

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
- **Free tier usage:** ~2,880 runs/month x ~45s (incl. overhead) = ~2,160 minutes. Close to the 2,000 min limit for private repos. Use `actions/cache` for pip to reduce setup time, or make the repo public for unlimited minutes.

## GitHub Actions Workflow

The workflow (`.github/workflows/check-mov.yml`):

```yaml
name: Check MOV Progress
on:
  schedule:
    - cron: '*/15 * * * *'
  workflow_dispatch: # allows manual trigger for testing

concurrency:
  group: mov-check
  cancel-in-progress: false  # let running job finish, queue the next

permissions:
  contents: write

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ hashFiles('requirements.txt') }}

      - run: pip install -r requirements.txt

      - run: python main.py
        env:
          QOGITA_EMAIL: ${{ secrets.QOGITA_EMAIL }}
          QOGITA_PASSWORD: ${{ secrets.QOGITA_PASSWORD }}
          TEAMS_WEBHOOK_URL: ${{ secrets.TEAMS_WEBHOOK_URL }}

      - name: Commit state changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add state.json
          git diff --cached --quiet || git commit -m "Update MOV notification state"
          git pull --rebase
          git push
```

Key details:
- `concurrency.group: mov-check` prevents overlapping runs (eliminates race conditions)
- `workflow_dispatch` allows manual triggering for testing
- `git diff --cached --quiet || git commit` only commits if `state.json` actually changed
- `git pull --rebase` before push handles any concurrent changes safely
- `actions/cache` for pip reduces workflow duration

## Teams Webhook Setup

1. Create a Teams channel for notifications (e.g., "Qogita MOV Alerts")
2. Add an "Incoming Webhook" connector to the channel
3. Name it (e.g., "Qogita Bot") and copy the webhook URL
4. Add the URL as a repository secret named `TEAMS_WEBHOOK_URL`

## Error Handling

- **No active cart:** log info message, exit cleanly (code 0). Not an error — just nothing to check.
- **Authentication failure:** log error, exit with non-zero code (workflow shows as failed).
- **API rate limit (429):** log warning with `Retry-After` value, exit (workflow retries next run).
- **Teams webhook failure:** log error, do not add allocation FID to `notified` list (will retry next run).
- **Malformed `state.json`:** treat as empty state, log warning. Bot will re-check all allocations (may send duplicates once, then state stabilizes).
- **`movProgress` field missing or non-numeric:** skip that allocation, log warning.

## Testing

- Unit tests for MOV detection logic (filtering allocations by movProgress, including edge cases: missing field, non-numeric value)
- Unit tests for state management (load/save, cart transition, malformed file)
- Unit tests for notification deduplication logic
- Integration test against live Qogita API (manual, using existing credentials)
