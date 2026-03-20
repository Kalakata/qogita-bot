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

    try:
        # Normalize headers: lowercase, strip non-ASCII prefixes (currency symbols)
        raw_reader = csv.DictReader(io.StringIO(resp.text))
        items = []
        for raw_row in raw_reader:
            row = {k.encode("ascii", "ignore").decode().lower().strip(): v for k, v in raw_row.items()}

            price = row.get("price inc. shipping") or row.get("price") or row.get("unit_price")
            if not price:
                continue
            try:
                price_f = float(price)
            except (ValueError, TypeError):
                continue

            # Extract fid and slug from Product URL if available
            # URL format: https://www.qogita.com/products/{fid}/{slug}/
            fid, slug = "", ""
            product_url = row.get("product url") or ""
            if "/products/" in product_url:
                parts = product_url.rstrip("/").split("/products/")[-1].split("/")
                if len(parts) >= 2:
                    fid, slug = parts[0], parts[1]

            try:
                qty = int(row.get("inventory") or row.get("available_quantity") or row.get("availablequantity") or 0)
            except (ValueError, TypeError):
                qty = 0

            items.append({
                "gtin": row.get("gtin") or row.get("ean") or "",
                "name": row.get("name") or "",
                "fid": fid,
                "slug": slug,
                "price": price,
                "priceCurrency": "EUR",
                "availableQuantity": qty,
                "discount": 0.0,  # No target price in CSV, discount computed later if needed
            })

        items.sort(key=lambda d: d["price"])
        return items
    except Exception:
        logger.exception("Failed to parse CSV for allocation %s", allocation_qid)
        return []
