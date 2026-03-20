# Cart Fill Suggestions — Design Spec

## Overview

Replace the hourly price drop alert with an actionable "Cart Fill Suggestions" notification that identifies watchlist items available from suppliers where cart allocations haven't reached MOV. This helps users fill their carts efficiently by showing items they already want, from suppliers where they need to spend more.

Reuses the existing `run_count % 60 == 0` trigger — no new state or counter needed.

## Data Flow

1. Every 60th run (hourly), fetch cart allocations (with `qid`)
2. Filter to allocations where `movProgress < 1.0`
3. Sort by gap (`mov - subtotal` ascending), take top 5 closest to MOV
4. For each allocation: `GET /variants/search/download/?cart_allocation_qid={qid}&show_watchlisted_only=true`
5. Parse CSV responses into lists of suggested items per allocation
6. Build one Teams Adaptive Card showing per-allocation suggestions
7. Write full results to `deals.csv` in repo, link at bottom of card

## API Changes

### `get_allocations()` — Updated

Also capture `qid` field from the API response. Non-breaking for callers, but existing test assertions on exact dict equality will need updating.

```python
allocations.append({
    "qid": a["qid"],       # NEW — needed for search endpoint
    "fid": a["fid"],
    "movProgress": a["movProgress"],
    "mov": a["mov"],
    "movCurrency": a["movCurrency"],
    "subtotal": a["subtotal"],
})
```

### `get_supplier_watchlist_items(token, allocation_qid)` — New

Calls `GET /variants/search/download/?cart_allocation_qid={qid}&show_watchlisted_only=true`.

- Response is CSV. The exact column headers are undocumented — implementation must inspect the response and map columns to our field names. Use the first row as headers and build dicts from each subsequent row.
- Returns list of dicts with at minimum: `gtin`, `name`, `price`, `priceCurrency`, `availableQuantity`
- `discount` is computed client-side as `1 - (price / targetPrice)` if a target price column exists, otherwise omitted. This avoids ambiguity about the API's discount format.
- Also captures `fid` and `slug` from CSV columns if available (needed for product URLs). If not present, GTIN-only text is shown without a link.
- Sorts by discount descending (biggest discounts first)
- On 429: raises `RateLimitError`
- On any other error: logs warning, returns empty list (graceful skip)

## Teams Card Layout

```
CART FILL SUGGESTIONS
5 allocations need items · 23 suggestions total

Allocation ABC123 · EUR 412 / 500 MOV
Gap: EUR 88.00
  L'Oreal Revitalift Cream
  3600523784431 · EUR 5.17 · -22%
  Nivea Soft Moisturizer
  4005808668854 · EUR 2.54 · -15%
  ...and 4 more from this supplier

Allocation DEF456 · EUR 280 / 300 MOV
Gap: EUR 20.00
  Maybelline Concealer Fair
  0000030150065 · EUR 3.84 · -18%

(remaining allocations...)

View full list (deals.csv)
```

### Card Rules

- Show all 5 allocations in the card (sorted by smallest gap first)
- Per allocation: up to 3 suggested items (sorted by biggest discount)
- Overflow text for remaining items per allocation
- GTINs are clickable links to Qogita product pages when `fid`/`slug` are available
- Allocations with zero matches are skipped
- If zero allocations have any suggestions, no notification is sent
- Full results (all allocations, all items) written to `deals.csv`

## Output CSV Schema (`deals.csv`)

```
allocation_fid, mov, subtotal, gap, gtin, name, price, currency, discount, available_qty
```

Each row is one suggested item, grouped by allocation. This gives the full picture across all allocations (not just top 5) and all items (not just top 3 per allocation).

## Rate Limit Strategy

- 5 sequential API calls (one per allocation), no parallelism
- If any call hits 429: stop processing remaining allocations
- The report shows however many allocations were successfully fetched
- Existing `RateLimitError` handling in `main()` catches the case where the initial API calls (login, allocations) are rate-limited

## Error Handling

| Scenario | Behavior |
|---|---|
| Allocation missing `qid` | Skip allocation |
| Search returns empty CSV | Skip allocation (no suggestions) |
| Search returns non-200 (not 429) | Log warning, skip allocation |
| Search returns 429 | Stop processing remaining allocations |
| CSV parsing fails | Log warning, skip allocation |
| All allocations at MOV | No notification sent |
| Zero suggestions across all allocations | No notification sent |

## Code Removal

The following are removed (replaced by new cart-fill logic):
- `get_watchlist_deals()` in `qogita_client.py`
- `send_price_drop_alert()` in `teams_notifier.py`
- Related test cases updated to test new functions

## File Changes

| File | Change |
|---|---|
| `qogita_client.py` | Add `qid` to `get_allocations()`; new `get_supplier_watchlist_items()`; remove `get_watchlist_deals()` |
| `main.py` | Replace price drop logic with cart-fill logic; update `write_deals_csv()` for new CSV schema |
| `teams_notifier.py` | Remove `send_price_drop_alert()`; new `send_cart_fill_suggestions()` |
| `tests/test_main.py` | Update price drop test to test cart-fill flow |
| `tests/test_teams_notifier.py` | Replace price drop card tests with cart-fill card tests |
| `tests/test_qogita_client.py` | Add test for `get_supplier_watchlist_items()`; update `get_allocations` tests for `qid` field |

**Unchanged:** `state.py`, `state.json`, workflow file, MOV alert logic.
