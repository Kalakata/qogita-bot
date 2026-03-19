# Qogita Teams MOV Notification Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python bot that polls the Qogita API for cart allocation MOV progress and sends Teams notifications when allocations reach their minimum order value.

**Architecture:** GitHub Actions cron job (every 15 min) runs a Python script that authenticates with Qogita, fetches cart allocations, detects MOV completion (`movProgress >= 1.0`), sends Teams webhook notifications for new completions, and persists notification state in a `state.json` file committed back to the repo.

**Tech Stack:** Python 3.11, `requests`, GitHub Actions, Microsoft Teams Incoming Webhooks

**Spec:** `docs/superpowers/specs/2026-03-19-qogita-teams-mov-bot-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `qogita_client.py` | Qogita API wrapper: login + fetch allocations |
| `teams_notifier.py` | Teams webhook: send MessageCard notifications |
| `state.py` | Load/save `state.json`, deduplication logic |
| `main.py` | Orchestration: tie all components together |
| `state.json` | Persisted notification state (committed by workflow) |
| `tests/test_qogita_client.py` | Tests for API wrapper |
| `tests/test_teams_notifier.py` | Tests for webhook sender |
| `tests/test_state.py` | Tests for state management |
| `tests/test_main.py` | Tests for orchestration logic |
| `.github/workflows/check-mov.yml` | GitHub Actions scheduled workflow |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for local development |
| `.gitignore` | Git ignore rules |

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `state.json`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
requests==2.32.*
pytest==8.*
```

- [ ] **Step 2: Create `.env.example`**

```
QOGITA_EMAIL=
QOGITA_PASSWORD=
TEAMS_WEBHOOK_URL=
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
venv/
.venv/
```

- [ ] **Step 4: Create initial `state.json`**

```json
{}
```

- [ ] **Step 5: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 6: Install dependencies**

Run: `pip install -r requirements.txt`

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example .gitignore state.json tests/__init__.py
git commit -m "scaffold: project structure and dependencies"
```

---

### Task 2: Qogita API client — login

**Files:**
- Create: `qogita_client.py`
- Create: `tests/test_qogita_client.py`

- [ ] **Step 1: Write failing test for login**

```python
# tests/test_qogita_client.py
from unittest.mock import patch, Mock
from qogita_client import login

API_URL = "https://api.qogita.com"


def test_login_returns_token_and_cart_qid():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "accessToken": "tok123",
        "user": {"activeCartQid": "cart-abc"},
    }

    with patch("qogita_client.requests.post", return_value=mock_resp) as mock_post:
        token, cart_qid = login("a@b.com", "pass")

    assert token == "tok123"
    assert cart_qid == "cart-abc"
    mock_post.assert_called_once_with(
        f"{API_URL}/auth/login/",
        json={"email": "a@b.com", "password": "pass"},
    )


def test_login_returns_none_cart_qid_when_value_is_none():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "accessToken": "tok123",
        "user": {"activeCartQid": None},
    }

    with patch("qogita_client.requests.post", return_value=mock_resp):
        token, cart_qid = login("a@b.com", "pass")

    assert token == "tok123"
    assert cart_qid is None


def test_login_returns_none_cart_qid_when_key_missing():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "accessToken": "tok123",
        "user": {},
    }

    with patch("qogita_client.requests.post", return_value=mock_resp):
        token, cart_qid = login("a@b.com", "pass")

    assert token == "tok123"
    assert cart_qid is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_qogita_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'qogita_client'`

- [ ] **Step 3: Implement login**

```python
# qogita_client.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_qogita_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add qogita_client.py tests/test_qogita_client.py
git commit -m "feat: add Qogita API client with login"
```

---

### Task 3: Qogita API client — get_allocations

**Files:**
- Modify: `qogita_client.py`
- Modify: `tests/test_qogita_client.py`

- [ ] **Step 1: Write failing test for single page of allocations**

Append to `tests/test_qogita_client.py`:

```python
from qogita_client import get_allocations


def test_get_allocations_single_page():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "results": [
            {
                "fid": "ABC123",
                "movProgress": "0.750",
                "mov": "1000.00",
                "movCurrency": "EUR",
                "subtotal": "750.00",
                "qid": "alloc-1",
                "lines": [],
            },
            {
                "fid": "DEF456",
                "movProgress": "1.100",
                "mov": "500.00",
                "movCurrency": "EUR",
                "subtotal": "550.00",
                "qid": "alloc-2",
                "lines": [],
            },
        ],
        "next": None,
    }

    with patch("qogita_client.requests.get", return_value=mock_resp) as mock_get:
        allocs = get_allocations("tok123", "cart-abc")

    assert len(allocs) == 2
    assert allocs[0] == {
        "fid": "ABC123",
        "movProgress": "0.750",
        "mov": "1000.00",
        "movCurrency": "EUR",
        "subtotal": "750.00",
    }
    assert allocs[1]["fid"] == "DEF456"
    mock_get.assert_called_once_with(
        f"{API_URL}/carts/cart-abc/allocations/",
        headers={"Authorization": "Bearer tok123"},
        params={"page": 1, "size": 50},
    )
```

- [ ] **Step 2: Write failing test for pagination**

Append to `tests/test_qogita_client.py`:

```python
def test_get_allocations_paginates():
    page1 = Mock()
    page1.status_code = 200
    page1.raise_for_status = Mock()
    page1.json.return_value = {
        "results": [
            {
                "fid": "A1",
                "movProgress": "0.5",
                "mov": "100.00",
                "movCurrency": "EUR",
                "subtotal": "50.00",
                "qid": "q1",
                "lines": [],
            }
        ],
        "next": "http://api.qogita.com/carts/cart-abc/allocations/?page=2&size=50",
    }

    page2 = Mock()
    page2.status_code = 200
    page2.raise_for_status = Mock()
    page2.json.return_value = {
        "results": [
            {
                "fid": "B2",
                "movProgress": "1.0",
                "mov": "200.00",
                "movCurrency": "EUR",
                "subtotal": "200.00",
                "qid": "q2",
                "lines": [],
            }
        ],
        "next": None,
    }

    with patch("qogita_client.requests.get", side_effect=[page1, page2]):
        allocs = get_allocations("tok123", "cart-abc")

    assert len(allocs) == 2
    assert allocs[0]["fid"] == "A1"
    assert allocs[1]["fid"] == "B2"
```

- [ ] **Step 3: Write failing test for 429 rate limit handling**

Append to `tests/test_qogita_client.py`:

```python
import requests as real_requests
import pytest
from qogita_client import RateLimitError


def test_get_allocations_raises_rate_limit_error_on_429():
    mock_resp = Mock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "60"}
    mock_resp.raise_for_status.side_effect = real_requests.HTTPError(response=mock_resp)

    with patch("qogita_client.requests.get", return_value=mock_resp):
        with pytest.raises(RateLimitError) as exc_info:
            get_allocations("tok123", "cart-abc")
    assert exc_info.value.retry_after == "60"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_qogita_client.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_allocations'` and `ImportError: cannot import name 'RateLimitError'`

- [ ] **Step 5: Implement get_allocations**

Add to `qogita_client.py`:

```python
class RateLimitError(Exception):
    """Raised when the API returns 429 Too Many Requests."""
    def __init__(self, retry_after: str | None = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s")
```

Then add the function:

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_qogita_client.py -v`
Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add qogita_client.py tests/test_qogita_client.py
git commit -m "feat: add get_allocations with pagination and rate limit handling"
```

---

### Task 4: State management

**Files:**
- Create: `state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write failing tests for state loading**

```python
# tests/test_state.py
import json
import os
from state import load_state, save_state

STATE_FILE = "state.json"


def test_load_state_returns_empty_when_file_missing(tmp_path):
    path = str(tmp_path / "state.json")
    state = load_state(path)
    assert state == {"cart_qid": None, "notified": []}


def test_load_state_returns_empty_when_file_malformed(tmp_path):
    path = str(tmp_path / "state.json")
    with open(path, "w") as f:
        f.write("not json{{{")
    state = load_state(path)
    assert state == {"cart_qid": None, "notified": []}


def test_load_state_returns_empty_when_file_is_empty_object(tmp_path):
    path = str(tmp_path / "state.json")
    with open(path, "w") as f:
        json.dump({}, f)
    state = load_state(path)
    assert state == {"cart_qid": None, "notified": []}


def test_load_state_reads_valid_state(tmp_path):
    path = str(tmp_path / "state.json")
    data = {"cart_qid": "cart-1", "notified": ["A", "B"]}
    with open(path, "w") as f:
        json.dump(data, f)
    state = load_state(path)
    assert state == data
```

- [ ] **Step 2: Write failing tests for state saving**

Append to `tests/test_state.py`:

```python
def test_save_state_writes_json(tmp_path):
    path = str(tmp_path / "state.json")
    data = {"cart_qid": "cart-1", "notified": ["X"]}
    save_state(path, data)
    with open(path) as f:
        loaded = json.load(f)
    assert loaded == data
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'state'`

- [ ] **Step 4: Implement state module**

```python
# state.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_state.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add state.py tests/test_state.py
git commit -m "feat: add state management for notification dedup"
```

---

### Task 5: Teams webhook notifier

**Files:**
- Create: `teams_notifier.py`
- Create: `tests/test_teams_notifier.py`

- [ ] **Step 1: Write failing test for send_notification**

```python
# tests/test_teams_notifier.py
from unittest.mock import patch, Mock
from teams_notifier import send_notification


def test_send_notification_posts_message_card():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = Mock()

    allocation = {
        "fid": "ABC123",
        "movProgress": "1.050",
        "mov": "2800.00",
        "movCurrency": "EUR",
        "subtotal": "2940.00",
    }

    with patch("teams_notifier.requests.post", return_value=mock_resp) as mock_post:
        send_notification("https://webhook.example.com/hook", allocation)

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs[0][0] == "https://webhook.example.com/hook"
    payload = call_kwargs[1]["json"]
    assert payload["@type"] == "MessageCard"
    assert "ABC123" in payload["text"]
    assert "2800.00" in payload["text"]
    assert "EUR" in payload["text"]


def test_send_notification_raises_on_failure():
    mock_resp = Mock()
    mock_resp.status_code = 400
    mock_resp.raise_for_status.side_effect = Exception("Bad Request")

    allocation = {
        "fid": "X",
        "movProgress": "1.0",
        "mov": "100.00",
        "movCurrency": "EUR",
        "subtotal": "100.00",
    }

    import pytest

    with patch("teams_notifier.requests.post", return_value=mock_resp):
        with pytest.raises(Exception):
            send_notification("https://webhook.example.com/hook", allocation)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_teams_notifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'teams_notifier'`

- [ ] **Step 3: Implement teams_notifier**

```python
# teams_notifier.py
import requests


def send_notification(webhook_url: str, allocation: dict) -> None:
    """Send a Teams notification for an allocation that reached MOV."""
    fid = allocation["fid"]
    mov = allocation["mov"]
    currency = allocation["movCurrency"]

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"Cart allocation {fid} reached MOV",
        "text": f"Cart allocation **{fid}** has reached its MOV! ({currency} {mov})",
    }

    resp = requests.post(webhook_url, json=payload)
    resp.raise_for_status()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_teams_notifier.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add teams_notifier.py tests/test_teams_notifier.py
git commit -m "feat: add Teams webhook notifier"
```

---

### Task 6: Main orchestration

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing test for main — happy path with new notifications**

```python
# tests/test_main.py
import json
from unittest.mock import patch, Mock, call
from main import run


def test_run_sends_notification_for_new_mov_reached(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({}, f)

    allocations = [
        {"fid": "A1", "movProgress": "1.05", "mov": "500.00", "movCurrency": "EUR", "subtotal": "525.00"},
        {"fid": "B2", "movProgress": "0.50", "mov": "1000.00", "movCurrency": "EUR", "subtotal": "500.00"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.send_notification") as mock_notify:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_notify.assert_called_once_with("https://hook.example.com", allocations[0])

    with open(state_path) as f:
        state = json.load(f)
    assert state["cart_qid"] == "cart-1"
    assert "A1" in state["notified"]
    assert "B2" not in state["notified"]


def test_run_skips_already_notified(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({"cart_qid": "cart-1", "notified": ["A1"]}, f)

    allocations = [
        {"fid": "A1", "movProgress": "1.05", "mov": "500.00", "movCurrency": "EUR", "subtotal": "525.00"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.send_notification") as mock_notify:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_notify.assert_not_called()


def test_run_resets_state_on_cart_change(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({"cart_qid": "old-cart", "notified": ["X1"]}, f)

    allocations = [
        {"fid": "A1", "movProgress": "1.00", "mov": "300.00", "movCurrency": "EUR", "subtotal": "300.00"},
    ]

    with patch("main.login", return_value=("tok", "new-cart")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.send_notification") as mock_notify:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_notify.assert_called_once()
    with open(state_path) as f:
        state = json.load(f)
    assert state["cart_qid"] == "new-cart"
    assert "A1" in state["notified"]


def test_run_exits_cleanly_when_no_active_cart(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({}, f)

    with patch("main.login", return_value=("tok", None)), \
         patch("main.get_allocations") as mock_alloc, \
         patch("main.send_notification") as mock_notify:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_alloc.assert_not_called()
    mock_notify.assert_not_called()


def test_run_skips_allocation_with_non_numeric_mov_progress(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({}, f)

    allocations = [
        {"fid": "BAD1", "movProgress": "N/A", "mov": "500.00", "movCurrency": "EUR", "subtotal": "0.00"},
        {"fid": "GOOD1", "movProgress": "1.05", "mov": "300.00", "movCurrency": "EUR", "subtotal": "315.00"},
        {"fid": "MISSING", "mov": "100.00", "movCurrency": "EUR", "subtotal": "0.00"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.send_notification") as mock_notify:
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    mock_notify.assert_called_once()
    call_alloc = mock_notify.call_args[0][1]
    assert call_alloc["fid"] == "GOOD1"


def test_run_does_not_save_fid_when_notification_fails(tmp_path):
    state_path = str(tmp_path / "state.json")
    with open(state_path, "w") as f:
        json.dump({}, f)

    allocations = [
        {"fid": "FAIL1", "movProgress": "1.10", "mov": "400.00", "movCurrency": "EUR", "subtotal": "440.00"},
    ]

    with patch("main.login", return_value=("tok", "cart-1")), \
         patch("main.get_allocations", return_value=allocations), \
         patch("main.send_notification", side_effect=Exception("webhook down")):
        run(
            email="a@b.com",
            password="pass",
            webhook_url="https://hook.example.com",
            state_path=state_path,
        )

    with open(state_path) as f:
        state = json.load(f)
    assert "FAIL1" not in state.get("notified", [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'main'` or `ImportError`

- [ ] **Step 3: Implement main.py**

```python
# main.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_main.py -v`
Expected: 5 passed

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: 19 passed (all tests across all modules)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add main orchestration with dedup and error handling"
```

---

### Task 7: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/check-mov.yml`

- [ ] **Step 1: Create workflow file**

```yaml
name: Check MOV Progress
on:
  schedule:
    - cron: '*/15 * * * *'
  workflow_dispatch:

concurrency:
  group: mov-check
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ hashFiles('requirements.txt') }}

      - run: pip install -r requirements.txt

      - run: python main.py
        env:
          QOGITA_EMAIL: ${{ secrets.QOGITA_EMAIL }}
          QOGITA_PASSWORD: ${{ secrets.QOGITA_PASSWORD }}
          TEAMS_WEBHOOK_URL: ${{ secrets.TEAMS_WEBHOOK_URL }}

      - name: Commit state changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add state.json
          git diff --cached --quiet || git commit -m "Update MOV notification state"
          git pull --rebase
          git push
```

- [ ] **Step 2: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/check-mov.yml'))" 2>&1 || echo "Install pyyaml: pip install pyyaml" && pip install pyyaml && python -c "import yaml; yaml.safe_load(open('.github/workflows/check-mov.yml')); print('YAML is valid')"`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/check-mov.yml
git commit -m "ci: add GitHub Actions workflow for MOV check"
```

---

### Task 8: Final integration test (manual)

- [ ] **Step 1: Run locally with real credentials**

Create a `.env` file (not committed) with your real Qogita credentials and a test webhook URL:

```bash
cp .env.example .env
# Edit .env with real values
```

Run: `QOGITA_EMAIL=... QOGITA_PASSWORD=... TEAMS_WEBHOOK_URL=... python main.py`

Check:
- Script authenticates successfully
- Allocations are fetched and logged
- `state.json` is updated with cart_qid and any notified FIDs
- If any allocations have reached MOV, a Teams message appears in the channel

- [ ] **Step 2: Run all tests one final time**

Run: `python -m pytest tests/ -v`
Expected: 12 passed

- [ ] **Step 3: Final commit if any adjustments were made**

```bash
git add -A
git diff --cached --quiet || git commit -m "fix: adjustments from integration testing"
```

---

### Task 9: Push to GitHub and configure secrets

- [ ] **Step 1: Create GitHub repo**

```bash
gh repo create qogita-bot --private --source=. --push
```

- [ ] **Step 2: Add repository secrets**

```bash
gh secret set QOGITA_EMAIL
gh secret set QOGITA_PASSWORD
gh secret set TEAMS_WEBHOOK_URL
```

- [ ] **Step 3: Trigger workflow manually to verify**

```bash
gh workflow run check-mov.yml
gh run watch
```

Check that the workflow runs successfully and `state.json` is committed if there were MOV changes.
