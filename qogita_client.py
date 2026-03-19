import requests

API_URL = "https://api.qogita.com"


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
