import json
import os

STATE_FILE = os.path.expanduser("~/.claude/context-iq-state.json")


def emit(text: str, fallback: str) -> None:
    try:
        print(text, end="")
    except UnicodeEncodeError:
        print(fallback, end="")


try:
    with open(STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)

    score = state.get("context_pressure_score", 100)
    tokens = state.get("total_tokens", 0)
    status = state.get("status", "fresh").upper()
    turns = state.get("turns", 0)
    icons = {
        "FRESH": ("\U0001F7E2", "OK"),
        "WARM": ("\U0001F7E1", "WARN"),
        "STRAINED": ("\U0001F7E0", "HIGH"),
        "CRITICAL": ("\U0001F534", "CRIT"),
    }
    icon, fallback_icon = icons.get(status, ("\U0001F7E2", "OK"))
    emit(
        f"{icon} IQ:{score:.0f} | {tokens:,}tok | {turns}turns",
        f"{fallback_icon} IQ:{score:.0f} | {tokens:,}tok | {turns}turns",
    )
except FileNotFoundError:
    emit("\U0001F9E0 ContextIQ ready", "ContextIQ ready")
except Exception:
    emit("\U0001F9E0 --", "--")
