import requests

API_URL = "https://api.qogita.com"


class RateLimitError(Exception):
    """Raised when the API returns 429 Too Many Requests."""
    def __init__(self, retry_after: str | None = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s")


def login(email: str, password: str) -> tuple[str, str | None]:
    """Authenticate with Qogita API. Returns (token, active_cart_qid)."""
    resp = requests.post(
        f"{API_URL}/auth/login/",
        json={"email": email, "password": password},
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["accessToken"]
    cart_qid = data["user"].get("activeCartQid")
    return token, cart_qid


def get_allocations(token: str, cart_qid: str) -> list[dict]:
    """Fetch all allocations for a cart, paginating through all pages."""
    headers = {"Authorization": f"Bearer {token}"}
    allocations = []
    page = 1

    while True:
        resp = requests.get(
            f"{API_URL}/carts/{cart_qid}/allocations/",
            headers=headers,
            params={"page": page, "size": 50},
        )
        if resp.status_code == 429:
            raise RateLimitError(retry_after=resp.headers.get("Retry-After"))
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        for a in results:
            allocations.append({
                "fid": a["fid"],
                "movProgress": a["movProgress"],
                "mov": a["mov"],
                "movCurrency": a["movCurrency"],
                "subtotal": a["subtotal"],
            })

        if not data.get("next"):
            break
        page += 1

    return allocations


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
