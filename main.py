import csv
import io
import logging
import os
import subprocess
import sys
from datetime import date

from qogita_client import login, get_allocations, get_watchlist_deals, RateLimitError
from teams_notifier import send_summary, send_price_drop_alert
from state import load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

STATE_PATH = "state.json"
GIST_ID = "105c03d69475231dcdd5bf4216b78746"


def update_gist(deals: list[dict]) -> str | None:
    """Update the GitHub Gist with full deals CSV. Returns the gist URL or None on failure."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["gtin", "name", "price", "currency", "target_price", "discount", "available_qty"])
    for d in deals:
        writer.writerow([
            d["gtin"], d["name"], d["price"], d["priceCurrency"],
            d["targetPrice"], f"{d['discount']:.0%}", d["availableQuantity"],
        ])

    csv_content = buf.getvalue()
    tmp_path = "/tmp/qogita_deals.csv"
    with open(tmp_path, "w") as f:
        f.write(csv_content)

    try:
        subprocess.run(
            ["gh", "gist", "edit", GIST_ID, "-f", "qogita_deals.csv", tmp_path],
            check=True, capture_output=True, text=True,
        )
        return f"https://gist.github.com/Kalakata/{GIST_ID}"
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.exception("Failed to update gist.")
        return None


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

    # --- Price drop check (every 5th run) ---
    run_count = state.get("run_count", 0) + 1
    state["run_count"] = run_count

    # Reset price alerts daily
    today = date.today().isoformat()
    if state.get("price_alerts_date") != today:
        state["price_alerts"] = {}
        state["price_alerts_date"] = today
        logger.info("Daily reset of price alerts.")

    if run_count % 5 == 0:
        try:
            deals = get_watchlist_deals(token)
            price_alerts = state.get("price_alerts", {})

            # Filter: only new deals or deals where price dropped further
            new_deals = []
            for deal in deals:
                prev_price = price_alerts.get(deal["gtin"])
                if prev_price is None or float(deal["price"]) < float(prev_price):
                    new_deals.append(deal)

            if new_deals:
                try:
                    gist_url = update_gist(new_deals) if len(new_deals) > 10 else None
                    send_price_drop_alert(webhook_url, new_deals, gist_url=gist_url)
                    for deal in new_deals:
                        price_alerts[deal["gtin"]] = deal["price"]
                    logger.info("Price drop alert: %d deals", len(new_deals))
                except Exception:
                    logger.exception("Failed to send price drop alert.")

            state["price_alerts"] = price_alerts
        except Exception:
            logger.exception("Failed to check watchlist prices.")

    save_state(state_path, state)


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
