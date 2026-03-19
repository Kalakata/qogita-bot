import json
import logging

logger = logging.getLogger(__name__)


def load_state(path: str) -> dict:
    """Load notification state from JSON file. Returns empty state on any error."""
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict) or "cart_qid" not in data:
            return {"cart_qid": None, "notified": []}
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"cart_qid": None, "notified": []}


def save_state(path: str, state: dict) -> None:
    """Save notification state to JSON file. Logs and continues on failure."""
    try:
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except OSError:
        logger.exception("Failed to save state to %s. Notifications may be re-sent next run.", path)
