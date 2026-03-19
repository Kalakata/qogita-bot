# Qogita Teams MOV Notification Bot — Design Spec

## Overview

A Python cron job that polls the Qogita Buyer API for cart allocation MOV (Minimum Order Value) progress and sends one-way notifications to a Microsoft Teams channel via an incoming webhook when any allocation reaches its MOV threshold.

## Problem

Monitoring cart allocations on Qogita requires manually checking the platform. The team needs automatic notifications when a supplier allocation in a cart reaches its MOV so they can act on it promptly.

## Solution

A lightweight Python script deployed as a Render Cron Job that:

1. Authenticates with the Qogita API
2. Fetches all allocations for the active cart
3. Detects allocations where `movProgress >= 1.0`
4. Sends a Teams notification for newly reached allocations
5. Tracks notified allocations to avoid duplicates

## Architecture

```
┌─────────────┐   poll every 5 min   ┌──────────────┐
│ Render Cron  │ ──────────────────── │ Qogita API   │
│ (Python)     │ ◄─────────────────── │              │
│              │   allocation data    │              │
│              │                      └──────────────┘
│              │
│              │   POST webhook       ┌─────────────────┐
│              │ ──────────────────── │ Teams Channel   │
└──────┬───────┘                      └─────────────────┘
       │
       │  read/write state
       ▼
┌──────────────┐
│ Render KV    │
│ Store        │
└──────────────┘
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
2. Authenticate with Qogita API
3. Fetch all allocations for the active cart
4. Filter for `movProgress >= 1.0`
5. Load previously notified set from Render KV store
6. For each newly reached allocation, send Teams notification
7. Update notified set in KV store

### State Tracking — Render Key-Value Store

- **Key:** `notified_allocations`
- **Value:** JSON-serialized set of allocation QIDs that have already been notified
- Prevents duplicate notifications across cron runs
- State resets naturally when a new cart is created (new cart QID = new allocations)

## Configuration

All via environment variables:

| Variable | Description |
|----------|-------------|
| `QOGITA_EMAIL` | Qogita account email |
| `QOGITA_PASSWORD` | Qogita account password |
| `TEAMS_WEBHOOK_URL` | Microsoft Teams incoming webhook URL |
| `RENDER_KV_URL` | Render Key-Value store internal URL |

## File Structure

```
qogita-bot/
├── main.py              # Entry point for cron job
├── qogita_client.py     # Qogita API wrapper
├── teams_notifier.py    # Teams webhook sender
├── requirements.txt     # requests
├── .env.example         # Template for env vars
└── .gitignore
```

## Deployment

- **Platform:** Render Cron Job
- **Schedule:** `*/5 * * * *` (every 5 minutes)
- **Runtime:** Python 3.11+
- **State:** Render Key-Value Store (free tier)
- **Dependencies:** `requests`

## Teams Webhook Setup

1. Create a Teams channel for notifications (e.g., "Qogita MOV Alerts")
2. Add an "Incoming Webhook" connector to the channel
3. Name it (e.g., "Qogita Bot") and copy the webhook URL
4. Set the URL as `TEAMS_WEBHOOK_URL` environment variable in Render

## Error Handling

- Authentication failure: log error, exit (cron will retry next run)
- API rate limit (429): log warning, exit (cron retries next run)
- Teams webhook failure: log error, do not mark allocation as notified (will retry next run)
- KV store unavailable: log error, continue without state (may send duplicate notifications)

## Testing

- Unit tests for MOV detection logic (filtering allocations by movProgress)
- Unit tests for notification deduplication logic
- Integration test against live Qogita API (manual, using existing credentials)
