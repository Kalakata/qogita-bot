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


def test_save_state_writes_json(tmp_path):
    path = str(tmp_path / "state.json")
    data = {"cart_qid": "cart-1", "notified": ["X"]}
    save_state(path, data)
    with open(path) as f:
        loaded = json.load(f)
    assert loaded == data
