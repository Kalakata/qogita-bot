# Price Drop Alerts — Design Spec

## Overview

Add watchlist price drop detection to the existing Qogita MOV bot. When items on the watchlist are priced 40%+ below target price, send a Teams notification.

## Problem

Good deals on the Qogita watchlist can appear and disappear quickly. Manual checking is impractical with 15,000+ watchlist items.

## Solution

Every 5th bot run (~5 minutes), fetch all watchlist items where targets are met, filter for items priced 40%+ below target, and send a separate "Price Drop Alert" card to Teams.

## API Details

- **Endpoint:** `GET /watchlist/items/?is_available=true&are_targets_met=true&page={n}&size=50`
- **Paginated:** ~64 pages, ~36 seconds to fetch all
- **Key fields per item:**
  - `gtin` — product identifier
  - `name` — product name
  - `price` — current price (string or null)
  - `priceCurrency` — currency code
  - `targetPrice` — user's target price (string)
  - `availableQuantity` — stock available

### Deal Detection Logic

```python
discount = 1 - (float(price) / float(target_price))
is_deal = discount >= 0.40  # 40%+ below target
```

## Changes to Existing Components

### `qogita_client.py` — Add `get_watchlist_deals()`

- `get_watchlist_deals(token, min_discount=0.40) -> list[dict]` — paginates through all watchlist items with `is_available=true&are_targets_met=true`, filters for items where price is `min_discount` (40%) or more below target price. Returns list of dicts with keys: `gtin`, `name`, `price`, `priceCurrency`, `targetPrice`, `availableQuantity`, `discount` (float, e.g., 0.48 for 48% off).

### `teams_notifier.py` — Add `send_price_drop_alert()`

- `send_price_drop_alert(webhook_url, deals) -> None` — sends an Adaptive Card with a list of deals. Each row shows: product name (truncated), target price, current price, discount percentage.

### `main.py` — Add price check every 5th run

- Increment `run_count` in state on every run
- When `run_count % 5 == 0`, call `get_watchlist_deals()` and check for new deals
- Only alert for deals not already in `state.price_alerts` (or where price dropped further)

### `state.json` — Extended schema

```json
{
  "cart_qid": "c722c553-...",
  "notified": ["577MOO"],
  "run_count": 4,
  "price_alerts": {
    "0000030114319": "3.52"
  }
}
```

- `run_count` — increments each run. Watchlist checked when `run_count % 5 == 0`.
- `price_alerts` — maps GTIN to the price we last alerted at. Re-alert only if price drops further below the already-alerted price.

## Card Format

```
PRICE DROP ALERT

3 items 40%+ below target

Product Name          target     now     discount
Maybelline Concealer  EUR 2.89   EUR 1.50   -48%
Rimmel Mascara        EUR 3.91   EUR 2.00   -49%
...
```

- Sorted by discount percentage (biggest deals first)
- Max 10 items per card to keep it readable
- Color: "Good" (green) for the discount percentage

## Error Handling

- Watchlist fetch failure: log error, skip price check this run (retry next eligible run)
- Individual item with missing/null price: skip
- Card send failure: don't update `price_alerts` state (retry next run)

## No Additional Setup Required

- Same GitHub Actions workflow
- Same cron-job.org trigger
- Same Teams webhook
- Same repo secrets
