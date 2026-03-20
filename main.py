import csv
import logging
import os
import subprocess
import sys
import time
from qogita_client import login, get_allocations, get_watchlist_gtins, get_supplier_catalog, RateLimitError
from teams_notifier import send_summary, send_cart_fill_suggestions
from state import load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

STATE_PATH = "state.json"
DEALS_CSV = "deals.csv"
MAX_ALLOCATIONS = 5


def write_deals_csv(suggestions: list[dict], path: str = DEALS_CSV) -> str | None:
    """Write cart fill suggestions to a CSV file. Returns the GitHub URL or None."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["allocation_fid", "mov", "subtotal", "gap", "gtin", "name", "price", "currency", "discount", "available_qty"])
        for s in suggestions:
            alloc = s["allocation"]
            for item in s["items"]:
                writer.writerow([
                    alloc["fid"], alloc["mov"], alloc["subtotal"],
                    f"{alloc['gap']:.2f}",
                    item["gtin"], item["name"], item["price"],
                    item["priceCurrency"],
                    f"{item['discount']:.0%}" if item.get("discount") else "",
                    item["availableQuantity"],
                ])

    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        return f"https://github.com/{repo}/blob/master/{path}"
    return None


def _commit_and_push(*paths: str) -> bool:
    """Stage, commit, and push specified files. Returns True on success."""
    try:
        subprocess.run(["git", "add", *paths], check=True, capture_output=True, text=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode == 0:
            return True  # Nothing to commit
        subprocess.run(
            ["git", "commit", "-m", "Update MOV notification state"],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(["git", "pull", "--rebase"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "push"], check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        logger.exception("Failed to commit and push state.")
        return False


def _fetch_with_retry(email: str, password: str, token: str, allocation_qid: str, max_retries: int = 3) -> tuple[str, list[dict]]:
    """Fetch supplier catalog with retry on rate limit.

    Returns (token, items) — token may be refreshed if rate limit wait is long.
    """
    for attempt in range(max_retries):
        try:
            return token, get_supplier_catalog(token, allocation_qid)
        except RateLimitError as e:
            wait = int(e.retry_after or 60)
            if attempt < max_retries - 1:
                logger.info("Rate limited, waiting %ds before retry (%d/%d)", wait, attempt + 1, max_retries)
                time.sleep(wait)
                # Re-authenticate if wait was long (token may have expired)
                if wait > 60:
                    token, _ = login(email, password)
                    logger.info("Re-authenticated after long rate limit wait")
            else:
                raise
    return token, []


def _get_cart_fill_suggestions(email: str, password: str, token: str, allocations: list[dict], watchlist_gtins: dict[str, dict]) -> list[dict]:
    """Find watchlist items that can fill unfilled allocations.

    Returns list of dicts: {allocation: {..., gap}, items: [...]}
    sorted by gap ascending (closest to MOV first).
    """
    unfilled = []
    for a in allocations:
        try:
            prog = float(a.get("movProgress", "0"))
            if prog < 1.0 and a.get("qid"):
                gap = float(a["mov"]) - float(a["subtotal"])
                if gap > 0:
                    unfilled.append((gap, a))
        except (ValueError, TypeError):
            continue

    logger.info("Cart fill: %d allocations, %d unfilled (with qid)", len(allocations), len(unfilled))

    unfilled.sort(key=lambda x: x[0])
    top = unfilled[:MAX_ALLOCATIONS]

    suggestions = []
    for gap, alloc in top:
        try:
            token, catalog = _fetch_with_retry(email, password, token, alloc["qid"])
        except RateLimitError:
            logger.warning("Rate limited during cart fill check (retries exhausted). Stopping.")
            break

        # Filter to only watchlisted items and compute discount from target price
        items = []
        for item in catalog:
            wl = watchlist_gtins.get(item["gtin"])
            if not wl:
                continue
            target = wl.get("targetPrice")
            if target:
                try:
                    target_f = float(target)
                    price_f = float(item["price"])
                    if target_f > 0:
                        item["discount"] = max(0.0, round(1 - (price_f / target_f), 4))
                except (ValueError, TypeError):
                    pass
            items.append(item)

        items.sort(key=lambda d: d["discount"], reverse=True)
        logger.info("  Allocation %s (gap %.2f): %d catalog / %d watchlisted", alloc["fid"], gap, len(catalog), len(items))

        if not items:
            continue

        suggestions.append({
            "allocation": {
                "qid": alloc["qid"],
                "fid": alloc["fid"],
                "mov": alloc["mov"],
                "movCurrency": alloc["movCurrency"],
                "subtotal": alloc["subtotal"],
                "gap": gap,
            },
            "items": items,
        })

    return suggestions


def run(email: str, password: str, webhook_url: str, state_path: str = STATE_PATH) -> None:
    state = load_state(state_path)

    token, cart_qid = login(email, password)

    if cart_qid is None:
        logger.info("No active cart. Nothing to check.")
        return

    # Reset state if cart changed
    if state.get("cart_qid") != cart_qid:
        logger.info("Cart changed from %s to %s. Resetting state.", state.get("cart_qid"), cart_qid)
        state = {"cart_qid": cart_qid, "notified": []}

    allocations = get_allocations(token, cart_qid)

    reached = []
    for a in allocations:
        try:
            if float(a.get("movProgress", "0")) >= 1.0:
                reached.append(a)
        except (ValueError, TypeError):
            logger.warning("Skipping allocation %s: invalid movProgress %r", a.get("fid"), a.get("movProgress"))

    notified = set(state.get("notified", []))
    newly_reached = [a for a in reached if a["fid"] not in notified]

    if newly_reached:
        try:
            send_summary(webhook_url, allocations, len(reached), newly_reached=newly_reached)
            for alloc in newly_reached:
                notified.add(alloc["fid"])
                logger.info("Notified: %s (MOV %s %s)", alloc["fid"], alloc["movCurrency"], alloc["mov"])
        except Exception:
            logger.exception("Failed to send notification. Will retry next run.")

    state["cart_qid"] = cart_qid
    state["notified"] = sorted(notified)

    # --- Cart fill suggestions (hourly = every 60th run) ---
    run_count = state.get("run_count", 0) + 1
    state["run_count"] = run_count

    # Save state immediately so the updated run_count is on disk
    save_state(state_path, state)

    if run_count % 60 == 0:
        # Commit+push state BEFORE sending notifications to prevent duplicate
        # alerts caused by race conditions between consecutive workflow runs
        _commit_and_push(state_path)

        try:
            # Fetch watchlist with retry (paginating 3000+ items can hit rate limits)
            for attempt in range(3):
                try:
                    watchlist_gtins = get_watchlist_gtins(token)
                    break
                except RateLimitError as e:
                    wait = int(e.retry_after or 60)
                    if attempt < 2:
                        logger.info("Rate limited fetching watchlist, waiting %ds (%d/3)", wait, attempt + 1)
                        time.sleep(wait)
                        if wait > 60:
                            token, _ = login(email, password)
                    else:
                        raise
            logger.info("Fetched %d watchlist GTINs", len(watchlist_gtins))
            suggestions = _get_cart_fill_suggestions(email, password, token, allocations, watchlist_gtins)
            if suggestions:
                csv_url = write_deals_csv(suggestions)
                send_cart_fill_suggestions(webhook_url, suggestions, full_list_url=csv_url)
                if csv_url:
                    _commit_and_push(state_path, DEALS_CSV)
                total = sum(len(s["items"]) for s in suggestions)
                logger.info("Cart fill suggestions: %d allocations, %d items", len(suggestions), total)
        except Exception:
            logger.exception("Failed to check cart fill suggestions.")


def main():
    email = os.environ.get("QOGITA_EMAIL")
    password = os.environ.get("QOGITA_PASSWORD")
    webhook_url = os.environ.get("TEAMS_WEBHOOK_URL")

    if not all([email, password, webhook_url]):
        logger.error("Missing required env vars: QOGITA_EMAIL, QOGITA_PASSWORD, TEAMS_WEBHOOK_URL")
        sys.exit(1)

    try:
        run(email, password, webhook_url)
    except RateLimitError as e:
        logger.warning("Rate limited by Qogita API. Retry after %s seconds.", e.retry_after)
        sys.exit(0)  # Exit cleanly — workflow will retry next run


if __name__ == "__main__":
    main()
