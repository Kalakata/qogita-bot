import json
from unittest.mock import patch, Mock, call
from main import run


def test_run_sends_summary_with_newly_reached(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({}, f)

    allocations = [
        {"qid": "q1", "fid": "A1", "movProgress": "1.05", "mov": "500.00", "movCurrency": "EUR", "subtotal": "525.00"},
        {"qid": "q2", "fid": "B2", "movProgress": "0.50", "mov": "1000.00", "movCurrency": "EUR", "subtotal": "500.00"},
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
        {"qid": "q1", "fid": "A1", "movProgress": "1.05", "mov": "500.00", "movCurrency": "EUR", "subtotal": "525.00"},
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
        {"qid": "q1", "fid": "A1", "movProgress": "1.00", "mov": "300.00", "movCurrency": "EUR", "subtotal": "300.00"},
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
        {"qid": "q1", "fid": "BAD1", "movProgress": "N/A", "mov": "500.00", "movCurrency": "EUR", "subtotal": "0.00"},
        {"qid": "q2", "fid": "GOOD1", "movProgress": "1.05", "mov": "300.00", "movCurrency": "EUR", "subtotal": "315.00"},
        {"qid": "q3", "fid": "MISSING", "mov": "100.00", "movCurrency": "EUR", "subtotal": "0.00"},
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
        {"qid": "q1", "fid": "FAIL1", "movProgress": "1.10", "mov": "400.00", "movCurrency": "EUR", "subtotal": "440.00"},
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


def test_run_sends_cart_fill_on_60th_run(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({"cart_qid": "cart-1", "notified": [], "run_count": 59}, f)

    allocations = [
        {"qid": "alloc-1", "fid": "X1", "movProgress": "0.50", "mov": "500.00", "movCurrency": "EUR", "subtotal": "250.00"},
    ]
    supplier_items = [
        {"gtin": "111", "name": "Deal", "price": "3.00", "priceCurrency": "EUR", "availableQuantity": 10, "discount": 0.70, "fid": "p1", "slug": "deal"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.get_supplier_watchlist_items", return_value=supplier_items) as mock_items, \
         patch("main.send_summary"), \
         patch("main.send_cart_fill_suggestions") as mock_fill, \
         patch("main._commit_and_push"):
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_items.assert_called_once_with("tok", "alloc-1")
    mock_fill.assert_called_once()
    suggestions = mock_fill.call_args[0][1]
    assert len(suggestions) == 1
    assert suggestions[0]["allocation"]["fid"] == "X1"
    assert abs(suggestions[0]["allocation"]["gap"] - 250.0) < 0.01
    assert suggestions[0]["items"] == supplier_items

    with open(state_path) as f:
        state = json.load(f)
    assert state["run_count"] == 60


def test_run_skips_cart_fill_on_non_60th_run(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({"cart_qid": "cart-1", "notified": [], "run_count": 2}, f)

    allocations = [
        {"qid": "alloc-1", "fid": "X1", "movProgress": "0.50", "mov": "500.00", "movCurrency": "EUR", "subtotal": "250.00"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.get_supplier_watchlist_items") as mock_items, \
         patch("main.send_summary"), \
         patch("main.send_cart_fill_suggestions") as mock_fill:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_items.assert_not_called()
    mock_fill.assert_not_called()

    with open(state_path) as f:
        state = json.load(f)
    assert state["run_count"] == 3
