"""Shared session state on disk.

State lives in ~/.claude/context-iq/ as one JSON file per session plus a
``latest.json`` pointer, so multiple concurrent sessions never clobber each
other. Writes are atomic (temp file + rename) so readers never see a
half-written file.
"""
import json
import os
import tempfile

STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "context-iq")
# Pre-0.2 releases used a single shared file; still read it as a last resort.
LEGACY_STATE_FILE = os.path.join(os.path.expanduser("~"), ".claude", "context-iq-state.json")


def _safe_session_id(session_id: str) -> str:
    return "".join(c for c in session_id if c.isalnum() or c in "-_")[:64] or "default"


def state_path(session_id: str = None) -> str:
    if session_id:
        return os.path.join(STATE_DIR, f"state-{_safe_session_id(session_id)}.json")
    return os.path.join(STATE_DIR, "latest.json")


def _atomic_write(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_state(data: dict, session_id: str = None) -> None:
    """Write state for a session and update the latest.json pointer."""
    try:
        if session_id:
            data = {**data, "session_id": session_id}
            _atomic_write(state_path(session_id), data)
        _atomic_write(state_path(None), data)
    except Exception:
        pass  # state is best-effort telemetry; never break the caller


def read_state(session_id: str = None) -> dict:
    """Read a session's state, or the most recent one if session_id is None.

    Returns {} when nothing has been written yet.
    """
    candidates = []
    if session_id:
        candidates.append(state_path(session_id))
    candidates.append(state_path(None))
    candidates.append(LEGACY_STATE_FILE)
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}
