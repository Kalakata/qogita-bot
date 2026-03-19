from unittest.mock import patch, Mock
from teams_notifier import send_notification


def test_send_notification_posts_message_card():
    mock_resp = Mock()
    mock_resp.status_code = 200
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
    call_kwargs = mock_post.call_args
    assert call_kwargs[0][0] == "https://webhook.example.com/hook"
    payload = call_kwargs[1]["json"]
    assert payload["type"] == "message"
    card = payload["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"
    text = card["body"][0]["text"]
    assert "ABC123" in text
    assert "2800.00" in text
    assert "EUR" in text


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
