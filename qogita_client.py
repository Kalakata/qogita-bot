import csv
import io
import logging
import requests

API_URL = "https://api.qogita.com"

logger = logging.getLogger(__name__)


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
                "qid": a.get("qid", ""),
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


def get_supplier_watchlist_items(token: str, allocation_qid: str) -> list[dict]:
    """Fetch watchlist items available from the same supplier as the given allocation.

    Calls the CSV search/download endpoint filtered by allocation QID.
    Returns list of item dicts sorted by discount descending.
    """
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{API_URL}/variants/search/download/",
        headers=headers,
        params={
            "cart_allocation_qid": allocation_qid,
            "show_watchlisted_only": "true",
        },
    )
    if resp.status_code == 429:
        raise RateLimitError(retry_after=resp.headers.get("Retry-After"))
    if not resp.ok:
        logger.warning("Search endpoint returned %s for allocation %s", resp.status_code, allocation_qid)
        return []

    # DEBUG: log raw response details
    lines = resp.text.strip().split("\n")
    logger.info("  CSV response: %d lines, headers: %s", len(lines), lines[0][:200] if lines else "(empty)")
    if len(lines) > 1:
        logger.info("  First data row: %s", lines[1][:200])

    try:
        reader = csv.DictReader(io.StringIO(resp.text))
        items = []
        for row in reader:
            price = row.get("price") or row.get("Price") or row.get("unit_price")
            target = row.get("targetPrice") or row.get("target_price") or row.get("Target Price")
            if not price:
                continue
            try:
                price_f = float(price)
            except (ValueError, TypeError):
                continue

            discount = 0.0
            if target:
                try:
                    target_f = float(target)
                    if target_f > 0:
                        discount = max(0.0, round(1 - (price_f / target_f), 4))
                except (ValueError, TypeError):
                    pass

            gtin = row.get("gtin") or row.get("GTIN") or row.get("ean") or ""
            items.append({
                "gtin": gtin,
                "name": row.get("name") or row.get("Name") or row.get("title") or "",
                "fid": row.get("fid") or row.get("FID") or "",
                "slug": row.get("slug") or row.get("Slug") or "",
                "price": price,
                "priceCurrency": row.get("priceCurrency") or row.get("currency") or row.get("Currency") or "EUR",
                "availableQuantity": int(row.get("availableQuantity") or row.get("available_quantity") or row.get("Available Quantity") or 0),
                "discount": discount,
            })

        items.sort(key=lambda d: d["discount"], reverse=True)
        return items
    except Exception:
        logger.exception("Failed to parse CSV for allocation %s", allocation_qid)
        return []
