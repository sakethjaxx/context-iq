import json
import os

import pytest

from contextiq import state


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_DIR", str(tmp_path / "context-iq"))
    monkeypatch.setattr(state, "LEGACY_STATE_FILE", str(tmp_path / "legacy.json"))
    yield tmp_path


def test_roundtrip_with_session_id():
    state.write_state({"score": 88}, session_id="abc-123")
    assert state.read_state("abc-123")["score"] == 88
    # latest pointer updated too
    assert state.read_state(None)["score"] == 88


def test_sessions_do_not_clobber_each_other():
    state.write_state({"score": 10}, session_id="one")
    state.write_state({"score": 20}, session_id="two")
    assert state.read_state("one")["score"] == 10
    assert state.read_state("two")["score"] == 20


def test_missing_state_returns_empty():
    assert state.read_state("nope") == {}


def test_corrupt_file_is_skipped(isolated_state_dir):
    state.write_state({"score": 5}, session_id="good")
    bad = state.state_path("bad")
    os.makedirs(os.path.dirname(bad), exist_ok=True)
    with open(bad, "w") as f:
        f.write("{not json")
    # bad session falls through to latest.json
    assert state.read_state("bad")["score"] == 5


def test_legacy_fallback(isolated_state_dir):
    with open(state.LEGACY_STATE_FILE, "w") as f:
        json.dump({"score": 77}, f)
    assert state.read_state(None)["score"] == 77


def test_session_id_is_sanitized():
    state.write_state({"score": 1}, session_id="../../evil")
    path = state.state_path("../../evil")
    assert ".." not in os.path.basename(path)
    assert os.path.dirname(path) == state.STATE_DIR
