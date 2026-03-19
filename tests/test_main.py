import json
from unittest.mock import patch, Mock, call
from main import run


def test_run_sends_summary_with_newly_reached(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({}, f)

    allocations = [
        {"fid": "A1", "movProgress": "1.05", "mov": "500.00", "movCurrency": "EUR", "subtotal": "525.00"},
        {"fid": "B2", "movProgress": "0.50", "mov": "1000.00", "movCurrency": "EUR", "subtotal": "500.00"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.send_summary") as mock_summary:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_summary.assert_called_once()
    call_kwargs = mock_summary.call_args
    assert call_kwargs[1]["newly_reached"][0]["fid"] == "A1"

    with open(state_path) as f:
        state = json.load(f)
    assert state["cart_qid"] == "cart-1"
    assert "A1" in state["notified"]
    assert "B2" not in state["notified"]


def test_run_skips_already_notified(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({"cart_qid": "cart-1", "notified": ["A1"]}, f)

    allocations = [
        {"fid": "A1", "movProgress": "1.05", "mov": "500.00", "movCurrency": "EUR", "subtotal": "525.00"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.send_summary") as mock_summary:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_summary.assert_not_called()


def test_run_resets_state_on_cart_change(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({"cart_qid": "old-cart", "notified": ["X1"]}, f)

    allocations = [
        {"fid": "A1", "movProgress": "1.00", "mov": "300.00", "movCurrency": "EUR", "subtotal": "300.00"},
    ]

    with patch("main.login", return_value=("tok", "new-cart")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.send_summary") as mock_summary:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_summary.assert_called_once()
    with open(state_path) as f:
        state = json.load(f)
    assert state["cart_qid"] == "new-cart"
    assert "A1" in state["notified"]


def test_run_exits_cleanly_when_no_active_cart(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({}, f)

    with patch("main.login", return_value=("tok", None)), \
         patch("main.get_allocations") as mock_alloc, \
         patch("main.send_summary") as mock_summary:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_alloc.assert_not_called()
    mock_summary.assert_not_called()


def test_run_skips_allocation_with_non_numeric_mov_progress(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({}, f)

    allocations = [
        {"fid": "BAD1", "movProgress": "N/A", "mov": "500.00", "movCurrency": "EUR", "subtotal": "0.00"},
        {"fid": "GOOD1", "movProgress": "1.05", "mov": "300.00", "movCurrency": "EUR", "subtotal": "315.00"},
        {"fid": "MISSING", "mov": "100.00", "movCurrency": "EUR", "subtotal": "0.00"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.send_summary") as mock_summary:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_summary.assert_called_once()
    newly = mock_summary.call_args[1]["newly_reached"]
    assert len(newly) == 1
    assert newly[0]["fid"] == "GOOD1"


def test_run_does_not_save_fid_when_notification_fails(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({}, f)

    allocations = [
        {"fid": "FAIL1", "movProgress": "1.10", "mov": "400.00", "movCurrency": "EUR", "subtotal": "440.00"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.send_summary", side_effect=Exception("webhook down")):
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    with open(state_path) as f:
        state = json.load(f)
    assert "FAIL1" not in state.get("notified", [])


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
