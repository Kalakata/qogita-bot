from unittest.mock import patch, Mock
from teams_notifier import send_notification, send_summary


def test_send_notification_posts_adaptive_card():
    mock_resp = Mock()
    mock_resp.status_code = 202
    mock_resp.raise_for_status = Mock()

    allocation = {
        "fid": "ABC123",
        "movProgress": "1.050",
        "mov": "2800.00",
        "movCurrency": "EUR",
        "subtotal": "2940.00",
    }

    with patch("teams_notifier.requests.post", return_value=mock_resp) as mock_post:
        send_notification("https://webhook.example.com/hook", allocation)

    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert payload["type"] == "message"
    card = payload["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"
    # Check that key info is present somewhere in the card body
    card_str = str(card["body"])
    assert "ABC123" in card_str
    assert "2800.00" in card_str
    assert "EUR" in card_str
    assert "MOV REACHED" in card_str


def test_send_notification_raises_on_failure():
    mock_resp = Mock()
    mock_resp.status_code = 400
    mock_resp.raise_for_status.side_effect = Exception("Bad Request")

    allocation = {
        "fid": "X",
        "movProgress": "1.0",
        "mov": "100.00",
        "movCurrency": "EUR",
        "subtotal": "100.00",
    }

    import pytest

    with patch("teams_notifier.requests.post", return_value=mock_resp):
        with pytest.raises(Exception):
            send_notification("https://webhook.example.com/hook", allocation)


def test_send_summary_posts_top_5():
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
