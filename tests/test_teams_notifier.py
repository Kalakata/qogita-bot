from unittest.mock import patch, Mock
from teams_notifier import send_summary, send_cart_fill_suggestions


def test_send_summary_posts_card():
    mock_resp = Mock()
    mock_resp.status_code = 202
    mock_resp.raise_for_status = Mock()

    allocations = [
        {"fid": "A1", "movProgress": "0.92", "mov": "2800.00", "movCurrency": "EUR", "subtotal": "2581.00"},
        {"fid": "B2", "movProgress": "0.86", "mov": "450.00", "movCurrency": "EUR", "subtotal": "387.00"},
        {"fid": "C3", "movProgress": "0.50", "mov": "600.00", "movCurrency": "EUR", "subtotal": "300.00"},
    ]

    with patch("teams_notifier.requests.post", return_value=mock_resp) as mock_post:
        send_summary("https://webhook.example.com/hook", allocations, reached_count=0)

    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    card = payload["attachments"][0]["content"]
    card_str = str(card["body"])
    assert "A1" in card_str
    assert "B2" in card_str
    assert "Cart Summary" in card_str
    assert "MOV REACHED" not in card_str  # no newly reached


def test_send_summary_with_newly_reached():
    mock_resp = Mock()
    mock_resp.status_code = 202
    mock_resp.raise_for_status = Mock()

    allocations = [
        {"fid": "DONE1", "movProgress": "1.05", "mov": "500.00", "movCurrency": "EUR", "subtotal": "525.00"},
        {"fid": "A1", "movProgress": "0.92", "mov": "2800.00", "movCurrency": "EUR", "subtotal": "2581.00"},
        {"fid": "B2", "movProgress": "0.86", "mov": "450.00", "movCurrency": "EUR", "subtotal": "387.00"},
    ]
    newly = [allocations[0]]

    with patch("teams_notifier.requests.post", return_value=mock_resp) as mock_post:
        send_summary("https://webhook.example.com/hook", allocations, reached_count=1, newly_reached=newly)

    payload = mock_post.call_args[1]["json"]
    card = payload["attachments"][0]["content"]
    card_str = str(card["body"])
    assert "MOV REACHED" in card_str
    assert "DONE1" in card_str
    assert "500.00" in card_str
    # Top 5 should NOT include DONE1 (reached carts excluded)
    # A1 and B2 should be in top 5
    assert "A1" in card_str
    assert "B2" in card_str


def test_send_summary_raises_on_failure():
    mock_resp = Mock()
    mock_resp.status_code = 400
    mock_resp.raise_for_status.side_effect = Exception("Bad Request")

    import pytest

    with patch("teams_notifier.requests.post", return_value=mock_resp):
        with pytest.raises(Exception):
            send_summary("https://webhook.example.com/hook", [], reached_count=0)


def test_send_cart_fill_suggestions_posts_card():
    mock_resp = Mock()
    mock_resp.status_code = 202
    mock_resp.raise_for_status = Mock()

    suggestions = [
        {
            "allocation": {"fid": "ABC123", "mov": "500.00", "movCurrency": "EUR", "subtotal": "412.00", "gap": 88.0},
            "items": [
                {"gtin": "111", "name": "Maybelline Concealer", "price": "5.17", "priceCurrency": "EUR", "discount": 0.22, "availableQuantity": 100, "fid": "p1", "slug": "maybelline-concealer"},
                {"gtin": "222", "name": "Nivea Soft", "price": "2.54", "priceCurrency": "EUR", "discount": 0.15, "availableQuantity": 50, "fid": "p2", "slug": "nivea-soft"},
            ],
        },
    ]

    with patch("teams_notifier.requests.post", return_value=mock_resp) as mock_post:
        send_cart_fill_suggestions("https://webhook.example.com/hook", suggestions)

    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    card = payload["attachments"][0]["content"]
    card_str = str(card["body"])
    assert "CART FILL" in card_str
    assert "ABC123" in card_str
    assert "88.00" in card_str
    assert "Maybelline" in card_str
    assert "5.17" in card_str
    assert "22%" in card_str


def test_send_cart_fill_suggestions_limits_items_per_allocation():
    mock_resp = Mock()
    mock_resp.status_code = 202
    mock_resp.raise_for_status = Mock()

    items = [
        {"gtin": str(i), "name": f"Product {i}", "price": "1.00", "priceCurrency": "EUR", "discount": 0.50, "availableQuantity": 10, "fid": "", "slug": ""}
        for i in range(6)
    ]

    suggestions = [
        {
            "allocation": {"fid": "ALLOC1", "mov": "1000.00", "movCurrency": "EUR", "subtotal": "500.00", "gap": 500.0},
            "items": items,
        },
    ]

    with patch("teams_notifier.requests.post", return_value=mock_resp) as mock_post:
        send_cart_fill_suggestions("https://webhook.example.com/hook", suggestions)

    payload = mock_post.call_args[1]["json"]
    card = payload["attachments"][0]["content"]
    card_str = str(card["body"])
    assert "Product 0" in card_str
    assert "Product 1" in card_str
    assert "Product 2" in card_str
    assert "Product 3" not in card_str  # Only top 3 shown
    assert "3 more" in card_str
