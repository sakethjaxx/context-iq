"""ContextIQ for Claude Code: status line, early-warning hook and health report.

    python contextiq.py statusline            Claude Code statusLine command (JSON on stdin)
    python contextiq.py hook                  Claude Code Stop hook (JSON on stdin)
    python contextiq.py health [--json]       Report for the current project's latest session
    python contextiq.py health --session ID   Report for one session

Standard library only. statusline and hook always exit 0 and never print
tracebacks unless CONTEXT_IQ_DEBUG=1, so a problem here can't break Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

import claude_code as cc
from meter import STATUS_RANK

STATE_REFRESH_SECONDS = 60


def _debug() -> bool:
    return os.environ.get("CONTEXT_IQ_DEBUG", "") not in ("", "0")


def _read_stdin_json() -> dict:
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace").strip()
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        if _debug():
            traceback.print_exc()
        return {}


def _write(text: str) -> None:
    # Claude Code decodes stdout as UTF-8; Windows consoles default to a legacy code page.
    out = getattr(sys.stdout, "buffer", None)
    if out is not None:
        out.write(text.encode("utf-8"))
        out.flush()
    else:
        sys.stdout.write(text)


# ── statusline ───────────────────────────────────────────────────────────

def statusline(payload: dict) -> str:
    if not payload:
        return cc.render_statusline(None)
    snap = cc.from_statusline_payload(payload)
    if not snap.has_usage:
        usage = cc.read_transcript_usage(payload.get("transcript_path"))
        if usage:
            snap.used_tokens, snap.output_tokens = usage["used"], usage["output"]
            snap.has_usage, snap.compacted = not usage["compacted"], usage["compacted"]
            snap.model = snap.model or usage["model"]
            snap.source = "transcript"
    _remember(snap)
    return cc.render_statusline(snap)


def _remember(snap: cc.Snapshot) -> None:
    """Persist the snapshot for the hook, dashboard and MCP server, skipping no-op writes."""
    if not snap.session_id:
        return
    old = cc.load_state(snap.session_id)
    if old and all(old.get(k) == getattr(snap, k) for k in ("used_tokens", "window", "model", "has_usage")) \
            and snap.updated_at - float(old.get("updated_at") or 0) < STATE_REFRESH_SECONDS:
        return
    cc.save_state(snap)


# ── hook ─────────────────────────────────────────────────────────────────

def warn_level():
    """Lowest status that triggers a warning (CONTEXT_IQ_WARN), or None when off."""
    level = (os.environ.get("CONTEXT_IQ_WARN") or "strained").strip().lower()
    return level if level in STATUS_RANK and level != "fresh" else None


def hook(payload: dict):
    """Stop hook: returns a warning when the session gets worse than it was, else None."""
    session_id = payload.get("session_id")
    snap = cc.resolve_snapshot(session_id, payload.get("transcript_path"), payload.get("cwd"))
    if snap is None or not snap.session_id:
        return None
    state = cc.load_state(snap.session_id) or {}
    last = state.get("last_warned")
    level = warn_level()
    message = None
    if snap.has_usage:
        rank, last_rank = STATUS_RANK[snap.status], STATUS_RANK.get(last, -1)
        threshold = STATUS_RANK[level] if level else len(STATUS_RANK)
        if rank >= threshold and rank > last_rank:
            message, last = cc.render_warning(snap), snap.status
        elif rank < last_rank:
            # Pressure fell (e.g. /compact): warn again if it climbs back.
            last = snap.status if rank >= threshold else None
    elif snap.compacted:
        last = None
    cc.save_state(snap, last_warned=last)
    if not state:
        cc.prune_states()
    return message


# ── health ───────────────────────────────────────────────────────────────

def health_snapshot(session_id: str = None, cwd: str = None):
    cwd = cwd or os.getcwd()
    sid = cc._safe_id(session_id)
    if not sid:
        state = cc.latest_state(cwd=cwd)
        if state:
            sid = state["session_id"]
        else:
            transcript = cc.latest_transcript_for_cwd(cwd)
            if transcript:
                sid = os.path.splitext(os.path.basename(transcript))[0]
    return cc.resolve_snapshot(sid, cwd=cwd) if sid else None


# ── entry point ──────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="contextiq", description="ContextIQ for Claude Code")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("statusline", help="status line command (reads Claude Code JSON on stdin)")
    sub.add_parser("hook", help="Stop hook (reads Claude Code JSON on stdin)")
    h = sub.add_parser("health", help="print the session's context health")
    h.add_argument("--session", help="Claude Code session id (default: latest in this directory)")
    h.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.command == "statusline":
        try:
            _write(statusline(_read_stdin_json()))
        except Exception:
            if _debug():
                traceback.print_exc()
            _write(f"{cc.BRAIN} ContextIQ --")
        return 0

    if args.command == "hook":
        try:
            message = hook(_read_stdin_json())
            if message:
                _write(json.dumps({"systemMessage": message}))
        except Exception:
            if _debug():
                traceback.print_exc()
        return 0

    if args.command == "health":
        snap = health_snapshot(args.session)
        if args.json:
            _write(json.dumps(snap.to_dict() if snap else {"error": "no usage recorded yet"}, indent=2) + "\n")
        else:
            _write(cc.render_report(snap) + "\n")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
