import logging
import os
import sys

from qogita_client import login, get_allocations, RateLimitError
from teams_notifier import send_notification
from state import load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

STATE_PATH = "state.json"


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

    for alloc in reached:
        fid = alloc["fid"]
        if fid in notified:
            continue

        try:
            send_notification(webhook_url, alloc)
            notified.add(fid)
            logger.info("Notified: %s (MOV %s %s)", fid, alloc["movCurrency"], alloc["mov"])
        except Exception:
            logger.exception("Failed to notify for %s. Will retry next run.", fid)

    state["cart_qid"] = cart_qid
    state["notified"] = sorted(notified)
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
