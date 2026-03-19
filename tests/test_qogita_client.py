from unittest.mock import patch, Mock
from qogita_client import login

API_URL = "https://api.qogita.com"


def test_login_returns_token_and_cart_qid():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "accessToken": "tok123",
        "user": {"activeCartQid": "cart-abc"},
    }

    with patch("qogita_client.requests.post", return_value=mock_resp) as mock_post:
        token, cart_qid = login("a@b.com", "pass")

    assert token == "tok123"
    assert cart_qid == "cart-abc"
    mock_post.assert_called_once_with(
        f"{API_URL}/auth/login/",
        json={"email": "a@b.com", "password": "pass"},
    )


def test_login_returns_none_cart_qid_when_value_is_none():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "accessToken": "tok123",
        "user": {"activeCartQid": None},
    }

    with patch("qogita_client.requests.post", return_value=mock_resp):
        token, cart_qid = login("a@b.com", "pass")

    assert token == "tok123"
    assert cart_qid is None


def test_login_returns_none_cart_qid_when_key_missing():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "accessToken": "tok123",
        "user": {},
    }

    with patch("qogita_client.requests.post", return_value=mock_resp):
        token, cart_qid = login("a@b.com", "pass")

    assert token == "tok123"
    assert cart_qid is None
