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
