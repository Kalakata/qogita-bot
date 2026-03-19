from unittest.mock import patch, Mock
from qogita_client import login
from qogita_client import get_allocations
from qogita_client import get_watchlist_deals
import requests as real_requests
import pytest
from qogita_client import RateLimitError

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


def test_get_allocations_single_page():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "results": [
            {
                "fid": "ABC123",
                "movProgress": "0.750",
                "mov": "1000.00",
                "movCurrency": "EUR",
                "subtotal": "750.00",
                "qid": "alloc-1",
                "lines": [],
            },
            {
                "fid": "DEF456",
                "movProgress": "1.100",
                "mov": "500.00",
                "movCurrency": "EUR",
                "subtotal": "550.00",
                "qid": "alloc-2",
                "lines": [],
            },
        ],
        "next": None,
    }

    with patch("qogita_client.requests.get", return_value=mock_resp) as mock_get:
        allocs = get_allocations("tok123", "cart-abc")

    assert len(allocs) == 2
    assert allocs[0] == {
        "fid": "ABC123",
        "movProgress": "0.750",
        "mov": "1000.00",
        "movCurrency": "EUR",
        "subtotal": "750.00",
    }
    assert allocs[1]["fid"] == "DEF456"
    mock_get.assert_called_once_with(
        f"{API_URL}/carts/cart-abc/allocations/",
        headers={"Authorization": "Bearer tok123"},
        params={"page": 1, "size": 50},
    )


def test_get_allocations_paginates():
    page1 = Mock()
    page1.status_code = 200
    page1.raise_for_status = Mock()
    page1.json.return_value = {
        "results": [
            {
                "fid": "A1",
                "movProgress": "0.5",
                "mov": "100.00",
                "movCurrency": "EUR",
                "subtotal": "50.00",
                "qid": "q1",
                "lines": [],
            }
        ],
        "next": "http://api.qogita.com/carts/cart-abc/allocations/?page=2&size=50",
    }

    page2 = Mock()
    page2.status_code = 200
    page2.raise_for_status = Mock()
    page2.json.return_value = {
        "results": [
            {
                "fid": "B2",
                "movProgress": "1.0",
                "mov": "200.00",
                "movCurrency": "EUR",
                "subtotal": "200.00",
                "qid": "q2",
                "lines": [],
            }
        ],
        "next": None,
    }

    with patch("qogita_client.requests.get", side_effect=[page1, page2]):
        allocs = get_allocations("tok123", "cart-abc")

    assert len(allocs) == 2
    assert allocs[0]["fid"] == "A1"
    assert allocs[1]["fid"] == "B2"


def test_get_allocations_raises_rate_limit_error_on_429():
    mock_resp = Mock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "60"}
    mock_resp.raise_for_status.side_effect = real_requests.HTTPError(response=mock_resp)

    with patch("qogita_client.requests.get", return_value=mock_resp):
        with pytest.raises(RateLimitError) as exc_info:
            get_allocations("tok123", "cart-abc")
    assert exc_info.value.retry_after == "60"


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
