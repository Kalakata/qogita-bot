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
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {"cart_qid": None, "notified": []}


def save_state(path: str, state: dict) -> None:
    """Save notification state to JSON file."""
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
