# Price Drop Alerts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add watchlist price drop detection (40%+ below target) to the existing Qogita MOV bot, checking every 5th run.

**Architecture:** Extend `qogita_client.py` with a watchlist fetch function, `teams_notifier.py` with a price drop card, and `main.py` with a run counter that triggers the price check every 5th run. State tracks alerted GTINs and prices to avoid duplicates.

**Tech Stack:** Python 3.11, `requests`, existing GitHub Actions workflow

**Spec:** `docs/superpowers/specs/2026-03-19-price-drop-alerts-design.md`

---

## File Map

| File | Change | Responsibility |
|------|--------|---------------|
| `qogita_client.py` | Modify | Add `get_watchlist_deals()` |
| `teams_notifier.py` | Modify | Add `send_price_drop_alert()` |
| `main.py` | Modify | Add run counter + price check logic |
| `tests/test_qogita_client.py` | Modify | Add tests for `get_watchlist_deals()` |
| `tests/test_teams_notifier.py` | Modify | Add test for `send_price_drop_alert()` |
| `tests/test_main.py` | Modify | Add tests for price check integration |

---

### Task 1: Add `get_watchlist_deals()` to API client

**Files:**
- Modify: `qogita_client.py`
- Modify: `tests/test_qogita_client.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_qogita_client.py`:

```python
from qogita_client import get_watchlist_deals


def test_get_watchlist_deals_filters_by_discount():
    page1 = Mock()
    page1.status_code = 200
    page1.raise_for_status = Mock()
    page1.json.return_value = {
        "results": [
            {
                "gtin": "111",
                "name": "Big Deal Product",
                "price": "3.00",
                "priceCurrency": "EUR",
                "targetPrice": "10.00",
                "availableQuantity": 100,
            },
            {
                "gtin": "222",
                "name": "Small Deal Product",
                "price": "8.00",
                "priceCurrency": "EUR",
                "targetPrice": "10.00",
                "availableQuantity": 50,
            },
            {
                "gtin": "333",
                "name": "No Price Product",
                "price": None,
                "priceCurrency": "EUR",
                "targetPrice": "5.00",
                "availableQuantity": 0,
            },
        ],
        "next": None,
    }

    with patch("qogita_client.requests.get", return_value=page1):
        deals = get_watchlist_deals("tok123", min_discount=0.40)

    # Only "Big Deal" qualifies: (10-3)/10 = 0.70 = 70% off
    # "Small Deal": (10-8)/10 = 0.20 = 20% off — below threshold
    # "No Price": skipped
    assert len(deals) == 1
    assert deals[0]["gtin"] == "111"
    assert deals[0]["name"] == "Big Deal Product"
    assert deals[0]["price"] == "3.00"
    assert deals[0]["targetPrice"] == "10.00"
    assert abs(deals[0]["discount"] - 0.70) < 0.01


def test_get_watchlist_deals_paginates():
    page1 = Mock()
    page1.status_code = 200
    page1.raise_for_status = Mock()
    page1.json.return_value = {
        "results": [
            {"gtin": "A", "name": "A", "price": "1.00", "priceCurrency": "EUR", "targetPrice": "10.00", "availableQuantity": 10},
        ],
        "next": "http://api.qogita.com/watchlist/items/?page=2",
    }
    page2 = Mock()
    page2.status_code = 200
    page2.raise_for_status = Mock()
    page2.json.return_value = {
        "results": [
            {"gtin": "B", "name": "B", "price": "2.00", "priceCurrency": "EUR", "targetPrice": "10.00", "availableQuantity": 5},
        ],
        "next": None,
    }

    with patch("qogita_client.requests.get", side_effect=[page1, page2]):
        deals = get_watchlist_deals("tok123", min_discount=0.40)

    assert len(deals) == 2
    assert deals[0]["gtin"] == "A"
    assert deals[1]["gtin"] == "B"


def test_get_watchlist_deals_raises_on_429():
    mock_resp = Mock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "30"}

    with patch("qogita_client.requests.get", return_value=mock_resp):
        with pytest.raises(RateLimitError):
            get_watchlist_deals("tok123")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_qogita_client.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_watchlist_deals'`

- [ ] **Step 3: Implement `get_watchlist_deals()`**

Add to `qogita_client.py`:

```python
def get_watchlist_deals(token: str, min_discount: float = 0.40) -> list[dict]:
    """Fetch watchlist items with price at least min_discount below target."""
    headers = {"Authorization": f"Bearer {token}"}
    deals = []
    page = 1

    while True:
        resp = requests.get(
            f"{API_URL}/watchlist/items/",
            headers=headers,
            params={"page": page, "size": 50, "is_available": "true", "are_targets_met": "true"},
        )
        if resp.status_code == 429:
            raise RateLimitError(retry_after=resp.headers.get("Retry-After"))
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        for item in results:
            price = item.get("price")
            target = item.get("targetPrice")
            if price is None or target is None:
                continue
            try:
                price_f = float(price)
                target_f = float(target)
                if target_f <= 0:
                    continue
                discount = 1 - (price_f / target_f)
                if discount >= min_discount:
                    deals.append({
                        "gtin": item["gtin"],
                        "name": item["name"],
                        "price": price,
                        "priceCurrency": item["priceCurrency"],
                        "targetPrice": target,
                        "availableQuantity": item["availableQuantity"],
                        "discount": round(discount, 4),
                    })
            except (ValueError, TypeError):
                continue

        if not data.get("next"):
            break
        page += 1

    deals.sort(key=lambda d: d["discount"], reverse=True)
    return deals
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_qogita_client.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add qogita_client.py tests/test_qogita_client.py
git commit -m "feat: add get_watchlist_deals with discount filtering"
```

---

### Task 2: Add `send_price_drop_alert()` to notifier

**Files:**
- Modify: `teams_notifier.py`
- Modify: `tests/test_teams_notifier.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_teams_notifier.py`:

```python
from teams_notifier import send_price_drop_alert


def test_send_price_drop_alert_posts_card():
    mock_resp = Mock()
    mock_resp.status_code = 202
    mock_resp.raise_for_status = Mock()

    deals = [
        {"gtin": "111", "name": "Maybelline Concealer 15 Fair", "price": "1.50", "priceCurrency": "EUR", "targetPrice": "2.89", "availableQuantity": 100, "discount": 0.4811},
        {"gtin": "222", "name": "Rimmel Mascara Volume", "price": "2.00", "priceCurrency": "EUR", "targetPrice": "3.91", "availableQuantity": 50, "discount": 0.4885},
    ]

    with patch("teams_notifier.requests.post", return_value=mock_resp) as mock_post:
        send_price_drop_alert("https://webhook.example.com/hook", deals)

    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    card = payload["attachments"][0]["content"]
    card_str = str(card["body"])
    assert "PRICE DROP" in card_str
    assert "Maybelline" in card_str
    assert "1.50" in card_str
    assert "2.89" in card_str
    assert "48%" in card_str


def test_send_price_drop_alert_limits_to_10():
    mock_resp = Mock()
    mock_resp.status_code = 202
    mock_resp.raise_for_status = Mock()

    deals = [
        {"gtin": str(i), "name": f"Product {i}", "price": "1.00", "priceCurrency": "EUR", "targetPrice": "10.00", "availableQuantity": 10, "discount": 0.90}
        for i in range(15)
    ]

    with patch("teams_notifier.requests.post", return_value=mock_resp) as mock_post:
        send_price_drop_alert("https://webhook.example.com/hook", deals)

    payload = mock_post.call_args[1]["json"]
    card = payload["attachments"][0]["content"]
    card_str = str(card["body"])
    # Should contain "Product 0" through "Product 9" but not "Product 10"
    assert "Product 9" in card_str
    assert "Product 10" not in card_str
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_teams_notifier.py -v`
Expected: FAIL — `ImportError: cannot import name 'send_price_drop_alert'`

- [ ] **Step 3: Implement `send_price_drop_alert()`**

Add to `teams_notifier.py`:

```python
def send_price_drop_alert(webhook_url: str, deals: list[dict]) -> None:
    """Send a price drop alert card to Teams. Max 10 items shown."""
    shown = deals[:10]

    card_body = [
        {
            "type": "TextBlock",
            "text": "PRICE DROP ALERT",
            "weight": "Bolder",
            "size": "Large",
            "color": "Good",
        },
        {
            "type": "TextBlock",
            "text": f"**{len(deals)} items** 40%+ below target",
            "spacing": "Small",
        },
    ]

    for deal in shown:
        discount_pct = f"-{deal['discount']:.0%}"
        card_body.append(
            {
                "type": "ColumnSet",
                "spacing": "Small",
                "columns": [
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"**{deal['name'][:40]}**",
                                "spacing": "None",
                                "wrap": True,
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "80px",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{deal['priceCurrency']} {deal['targetPrice']}",
                                "spacing": "None",
                                "isSubtle": True,
                                "horizontalAlignment": "Right",
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "80px",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"{deal['priceCurrency']} {deal['price']}",
                                "spacing": "None",
                                "weight": "Bolder",
                                "horizontalAlignment": "Right",
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "50px",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": discount_pct,
                                "spacing": "None",
                                "color": "Good",
                                "weight": "Bolder",
                                "horizontalAlignment": "Right",
                            }
                        ],
                    },
                ],
            }
        )

    if len(deals) > 10:
        card_body.append(
            {
                "type": "TextBlock",
                "text": f"*...and {len(deals) - 10} more*",
                "isSubtle": True,
                "spacing": "Small",
            }
        )

    _post_card(webhook_url, card_body)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_teams_notifier.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add teams_notifier.py tests/test_teams_notifier.py
git commit -m "feat: add price drop alert card"
```

---

### Task 3: Integrate price check into main.py

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_main.py`:

```python
def test_run_checks_prices_on_5th_run(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({"cart_qid": "cart-1", "notified": [], "run_count": 4}, f)

    allocations = [
        {"fid": "X1", "movProgress": "0.50", "mov": "500.00", "movCurrency": "EUR", "subtotal": "250.00"},
    ]
    deals = [
        {"gtin": "111", "name": "Deal", "price": "3.00", "priceCurrency": "EUR", "targetPrice": "10.00", "availableQuantity": 10, "discount": 0.70},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.get_watchlist_deals", return_value=deals) as mock_deals, \
         patch("main.send_summary") as mock_summary, \
         patch("main.send_price_drop_alert") as mock_price:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_deals.assert_called_once()
    mock_price.assert_called_once()

    with open(state_path) as f:
        state = json.load(f)
    assert state["run_count"] == 5
    assert "111" in state.get("price_alerts", {})


def test_run_skips_prices_on_non_5th_run(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({"cart_qid": "cart-1", "notified": [], "run_count": 2}, f)

    allocations = [
        {"fid": "X1", "movProgress": "0.50", "mov": "500.00", "movCurrency": "EUR", "subtotal": "250.00"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.get_watchlist_deals") as mock_deals, \
         patch("main.send_summary"), \
         patch("main.send_price_drop_alert") as mock_price:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_deals.assert_not_called()
    mock_price.assert_not_called()

    with open(state_path) as f:
        state = json.load(f)
    assert state["run_count"] == 3


def test_run_skips_already_alerted_price(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({"cart_qid": "cart-1", "notified": [], "run_count": 4, "price_alerts": {"111": "3.00"}}, f)

    allocations = [
        {"fid": "X1", "movProgress": "0.50", "mov": "500.00", "movCurrency": "EUR", "subtotal": "250.00"},
    ]
    deals = [
        {"gtin": "111", "name": "Deal", "price": "3.00", "priceCurrency": "EUR", "targetPrice": "10.00", "availableQuantity": 10, "discount": 0.70},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.get_watchlist_deals", return_value=deals), \
         patch("main.send_summary"), \
         patch("main.send_price_drop_alert") as mock_price:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_price.assert_not_called()


def test_run_realerts_when_price_drops_further(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({"cart_qid": "cart-1", "notified": [], "run_count": 4, "price_alerts": {"111": "3.00"}}, f)

    allocations = [
        {"fid": "X1", "movProgress": "0.50", "mov": "500.00", "movCurrency": "EUR", "subtotal": "250.00"},
    ]
    deals = [
        {"gtin": "111", "name": "Deal", "price": "2.00", "priceCurrency": "EUR", "targetPrice": "10.00", "availableQuantity": 10, "discount": 0.80},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.get_watchlist_deals", return_value=deals), \
         patch("main.send_summary"), \
         patch("main.send_price_drop_alert") as mock_price:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_price.assert_called_once()
    with open(state_path) as f:
        state = json.load(f)
    assert state["price_alerts"]["111"] == "2.00"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL — `ImportError` or `AttributeError`

- [ ] **Step 3: Update `main.py`**

Update imports:

```python
from qogita_client import login, get_allocations, get_watchlist_deals, RateLimitError
from teams_notifier import send_summary, send_price_drop_alert
```

Add price check logic at the end of `run()`, before `save_state()`:

```python
    # --- Price drop check (every 5th run) ---
    run_count = state.get("run_count", 0) + 1
    state["run_count"] = run_count

    if run_count % 5 == 0:
        try:
            deals = get_watchlist_deals(token)
            price_alerts = state.get("price_alerts", {})

            # Filter: only new deals or deals where price dropped further
            new_deals = []
            for deal in deals:
                prev_price = price_alerts.get(deal["gtin"])
                if prev_price is None or float(deal["price"]) < float(prev_price):
                    new_deals.append(deal)

            if new_deals:
                try:
                    send_price_drop_alert(webhook_url, new_deals)
                    for deal in new_deals:
                        price_alerts[deal["gtin"]] = deal["price"]
                    logger.info("Price drop alert: %d deals", len(new_deals))
                except Exception:
                    logger.exception("Failed to send price drop alert.")

            state["price_alerts"] = price_alerts
        except Exception:
            logger.exception("Failed to check watchlist prices.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_main.py -v`
Expected: 10 passed

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: integrate price drop check every 5th run"
```

---

### Task 4: End-to-end test and push

- [ ] **Step 1: Run locally with real credentials**

```bash
QOGITA_EMAIL=... QOGITA_PASSWORD=... TEAMS_WEBHOOK_URL=... python main.py
```

Verify: state.json has `run_count: 1`, no price alert yet (first run).

- [ ] **Step 2: Force a price check by setting run_count to 4**

Edit `state.json`: set `"run_count": 4`, then run again. Verify price drop card appears in Teams if any deals exist.

- [ ] **Step 3: Push**

```bash
git pull --rebase origin master
git push origin master
```
