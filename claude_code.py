"""Exact context usage from Claude Code, plus per-session state.

Claude Code already measures the context window: it sends the numbers to the
status line on stdin and records every API response's usage in the session
transcript. This module reads those numbers instead of asking the model to
estimate them.

Standard library only, and nothing here should raise: the status line runs on
every refresh and the hook after every response.
"""
from __future__ import annotations

import glob
import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass

from meter import (
    RECOMMENDATIONS,
    effective_window,
    quality_window,
    score_for_pressure,
    status_for_score,
)

ONE_MILLION = 1_000_000
CLAUDE_CODE_DEFAULT_WINDOW = 200_000
# Models Claude Code runs with a native 1M window, no [1m] suffix needed.
_NATIVE_1M = re.compile(r"^claude-(fable|mythos|opus-(4-[7-9]|[5-9])|sonnet-[5-9]|haiku-[5-9])")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

STATE_MAX_AGE = 14 * 24 * 3600
_TAIL_CHUNK = 64 * 1024
_TAIL_LIMIT = 16 * 1024 * 1024

ICONS = {"fresh": "\U0001F7E2", "warm": "\U0001F7E1", "strained": "\U0001F7E0", "critical": "\U0001F534"}
BRAIN = "\U0001F9E0"


# ── paths ────────────────────────────────────────────────────────────────

def config_dir() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def data_dir() -> str:
    return os.path.join(config_dir(), "context-iq")


def state_dir() -> str:
    return os.path.join(data_dir(), "sessions")


def _safe_id(session_id) -> str:
    return session_id if isinstance(session_id, str) and _SAFE_ID.match(session_id) else ""


def project_key(cwd: str) -> str:
    """Claude Code's folder name for a project under ~/.claude/projects/."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd or "")


def find_transcript(session_id: str):
    sid = _safe_id(session_id)
    if not sid:
        return None
    matches = glob.glob(os.path.join(config_dir(), "projects", "*", sid + ".jsonl"))
    return max(matches, key=_mtime) if matches else None


def latest_transcript_for_cwd(cwd: str):
    if not cwd:
        return None
    matches = glob.glob(os.path.join(config_dir(), "projects", project_key(cwd), "*.jsonl"))
    return max(matches, key=_mtime) if matches else None


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


# ── context window ───────────────────────────────────────────────────────

def _int(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def default_window(model: str):
    """Claude Code's window for a model when Claude Code didn't report one."""
    override = _int(os.environ.get("CLAUDE_CODE_MAX_CONTEXT_TOKENS"))
    if override:
        return override, "env"
    m = (model or "").lower()
    if "[1m]" in m:
        return ONE_MILLION, "model"
    if os.environ.get("CLAUDE_CODE_DISABLE_1M_CONTEXT", "") not in ("", "0", "false"):
        return CLAUDE_CODE_DEFAULT_WINDOW, "model"
    idx = m.find("claude-")
    if idx >= 0 and _NATIVE_1M.match(m[idx:]):
        return ONE_MILLION, "model"
    return CLAUDE_CODE_DEFAULT_WINDOW, "default"


# ── snapshot ─────────────────────────────────────────────────────────────

@dataclass
class Snapshot:
    session_id: str = ""
    model: str = ""
    model_name: str = ""
    cwd: str = ""
    project_dir: str = ""
    used_tokens: int = 0          # input + cache reads + cache writes, as Claude Code counts it
    output_tokens: int = 0
    window: int = CLAUDE_CODE_DEFAULT_WINDOW
    window_source: str = "default"  # claude-code | model | env | inferred | default
    source: str = ""              # statusline | transcript
    has_usage: bool = False
    compacted: bool = False       # just compacted; no response since
    updated_at: float = 0.0

    @property
    def scored_window(self) -> int:
        return max(1, effective_window(self.window))

    @property
    def window_pct(self) -> float:
        return 100.0 * self.used_tokens / self.window if self.window else 0.0

    @property
    def pressure(self) -> float:
        return min(1.0, self.used_tokens / self.scored_window)

    @property
    def score(self) -> float:
        return score_for_pressure(self.pressure)

    @property
    def status(self) -> str:
        return status_for_score(self.score)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(
            score=self.score,
            status=self.status,
            pressure_pct=round(100 * self.pressure, 1),
            window_pct=round(self.window_pct, 1),
            scored_window=self.scored_window,
            recommendation=RECOMMENDATIONS[self.status] if self.has_usage else "",
        )
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in (d or {}).items() if k in fields})


def from_statusline_payload(payload: dict) -> Snapshot:
    """Build a snapshot from the JSON Claude Code sends to the status line."""
    model = payload.get("model") or {}
    workspace = payload.get("workspace") or {}
    cw = payload.get("context_window") or {}
    snap = Snapshot(
        session_id=_safe_id(payload.get("session_id")),
        model=model.get("id") or "",
        model_name=model.get("display_name") or "",
        cwd=workspace.get("current_dir") or payload.get("cwd") or "",
        project_dir=workspace.get("project_dir") or "",
        source="statusline",
        updated_at=time.time(),
    )
    size = _int(cw.get("context_window_size"))
    if size:
        snap.window, snap.window_source = size, "claude-code"
    else:
        snap.window, snap.window_source = default_window(snap.model)

    usage = cw.get("current_usage")
    if isinstance(usage, dict):
        snap.used_tokens = (_int(usage.get("input_tokens"))
                            + _int(usage.get("cache_creation_input_tokens"))
                            + _int(usage.get("cache_read_input_tokens")))
        snap.output_tokens = _int(usage.get("output_tokens"))
        snap.has_usage = True
    elif "current_usage" not in cw and cw.get("used_percentage") is not None:
        try:
            snap.used_tokens = int(round(float(cw["used_percentage"]) / 100 * snap.window))
            snap.has_usage = True
        except (TypeError, ValueError):
            pass
    return snap


def read_transcript_usage(path: str):
    """Latest main-conversation usage from a transcript, read from the end.

    Returns {"used", "output", "model", "cwd", "compacted"} or None. A compaction
    boundary newer than the last response means the old usage no longer applies.
    """
    try:
        fh = open(path, "rb")
    except (OSError, TypeError):
        return None
    with fh:
        try:
            fh.seek(0, os.SEEK_END)
            pos = fh.tell()
        except OSError:
            return None
        carry = b""
        scanned = 0
        while pos > 0 and scanned < _TAIL_LIMIT:
            step = min(_TAIL_CHUNK, pos)
            pos -= step
            fh.seek(pos)
            chunk = fh.read(step) + carry
            scanned += step
            lines = chunk.split(b"\n")
            carry = lines.pop(0) if pos > 0 else b""
            for line in reversed(lines):
                found = _usage_from_line(line)
                if found is not None:
                    return found
        if carry:
            return _usage_from_line(carry)
    return None


def _usage_from_line(line: bytes):
    if b"compact_boundary" not in line and b'"usage"' not in line:
        return None
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict):
        return None
    if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
        return {"used": 0, "output": 0, "model": "", "cwd": entry.get("cwd") or "", "compacted": True}
    if entry.get("type") != "assistant" or entry.get("isSidechain") or entry.get("isApiErrorMessage"):
        return None
    message = entry.get("message") or {}
    usage = message.get("usage") or {}
    used = (_int(usage.get("input_tokens"))
            + _int(usage.get("cache_creation_input_tokens"))
            + _int(usage.get("cache_read_input_tokens")))
    output = _int(usage.get("output_tokens"))
    if not used and not output:   # synthetic/error placeholder
        return None
    return {"used": used, "output": output, "model": message.get("model") or "",
            "cwd": entry.get("cwd") or "", "compacted": False}


def resolve_snapshot(session_id: str, transcript_path: str = None, cwd: str = None):
    """Freshest snapshot for a session: transcript usage + the best known window."""
    sid = _safe_id(session_id)
    state = load_state(sid) if sid else None
    path = transcript_path or (find_transcript(sid) if sid else None)
    usage = read_transcript_usage(path) if path else None
    if usage is None:
        return Snapshot.from_dict(state) if state else None

    snap = Snapshot(
        session_id=sid,
        model=usage["model"] or (state or {}).get("model", ""),
        model_name=(state or {}).get("model_name", ""),
        cwd=cwd or usage["cwd"] or (state or {}).get("cwd", ""),
        project_dir=(state or {}).get("project_dir", ""),
        used_tokens=usage["used"],
        output_tokens=usage["output"],
        source="transcript",
        has_usage=not usage["compacted"],
        compacted=usage["compacted"],
        updated_at=time.time(),
    )
    # The status line records the exact window; reuse it while the model is the same.
    if state and state.get("window_source") == "claude-code" and (
            not snap.model or _same_model(state.get("model", ""), snap.model)):
        snap.window, snap.window_source = _int(state.get("window")) or CLAUDE_CODE_DEFAULT_WINDOW, "claude-code"
    else:
        snap.window, snap.window_source = default_window(snap.model)
    if snap.used_tokens > snap.window:
        snap.window = ONE_MILLION if snap.used_tokens <= ONE_MILLION else snap.used_tokens
        snap.window_source = "inferred"
    return snap


def _same_model(a: str, b: str) -> bool:
    strip = lambda m: re.sub(r"\[[^\]]*\]$", "", (m or "").lower())
    return strip(a) == strip(b)


# ── state store ──────────────────────────────────────────────────────────

def _state_path(session_id: str) -> str:
    return os.path.join(state_dir(), session_id + ".json")


def load_state(session_id: str):
    sid = _safe_id(session_id)
    if not sid:
        return None
    try:
        with open(_state_path(sid), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def save_state(snap: Snapshot, **extra) -> bool:
    """Merge the snapshot into the session's state file (atomic replace)."""
    if not snap.session_id:
        return False
    data = load_state(snap.session_id) or {}
    data.update(snap.to_dict())
    data.update(extra)
    return write_json_atomic(_state_path(snap.session_id), data)


def write_json_atomic(path: str, data, ensure_ascii: bool = True) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=ensure_ascii)
                fh.write("\n")
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return True
    except OSError:
        return False


def iter_states():
    for path in glob.glob(os.path.join(state_dir(), "*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("session_id"):
            yield data


def latest_state(cwd: str = None, max_age: float = None):
    """Most recently updated session, optionally limited to one project dir."""
    now = time.time()
    best = None
    for data in iter_states():
        if cwd and cwd not in (data.get("cwd"), data.get("project_dir")):
            continue
        if max_age is not None and now - float(data.get("updated_at") or 0) > max_age:
            continue
        if best is None or float(data.get("updated_at") or 0) > float(best.get("updated_at") or 0):
            best = data
    return best


def prune_states(max_age: float = STATE_MAX_AGE) -> None:
    cutoff = time.time() - max_age
    for path in glob.glob(os.path.join(state_dir(), "*.json")):
        if _mtime(path) < cutoff:
            try:
                os.remove(path)
            except OSError:
                pass


# ── rendering ────────────────────────────────────────────────────────────

def fmt_tokens(n: int) -> str:
    if n >= ONE_MILLION:
        v = n / ONE_MILLION
        return f"{v:.1f}M".replace(".0M", "M")
    if n >= 10_000:
        return f"{round(n / 1000):.0f}k"
    if n >= 1000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return str(n)


def render_statusline(snap: Snapshot) -> str:
    if snap is None or not snap.has_usage:
        if snap is not None and snap.compacted:
            return f"{BRAIN} IQ:-- compacted | waiting for next reply"
        return f"{BRAIN} ContextIQ ready"
    line = (f"{ICONS[snap.status]} IQ:{snap.score:.0f} {snap.status} | "
            f"{fmt_tokens(snap.used_tokens)}/{fmt_tokens(snap.window)} ctx")
    hint = {"strained": " | /compact soon", "critical": " | /compact now"}.get(snap.status)
    return line + (hint or "")


def render_warning(snap: Snapshot) -> str:
    return (f"{ICONS[snap.status]} ContextIQ: {snap.status} context ({fmt_tokens(snap.used_tokens)} tokens, "
            f"IQ {snap.score:.0f}/100). {RECOMMENDATIONS[snap.status]}")


def render_report(snap: Snapshot) -> str:
    if snap is None:
        return ("ContextIQ: no usage recorded for this session yet. "
                "It appears after Claude's first reply.")
    if not snap.has_usage:
        return ("ContextIQ: the conversation was just compacted; usage refreshes "
                "after the next reply.")
    lines = [
        f"ContextIQ score: {snap.score:.0f}/100 ({snap.status})",
        f"Context in use: {snap.used_tokens:,} tokens = {snap.window_pct:.1f}% of the "
        f"{snap.window:,}-token window ({snap.window_source})",
    ]
    if snap.scored_window < snap.window:
        lines.append(f"Quality horizon: {snap.scored_window:,} tokens; pressure {100 * snap.pressure:.1f}% "
                     f"(set CONTEXT_IQ_QUALITY_WINDOW to change)")
    if snap.model:
        lines.append(f"Model: {snap.model_name or snap.model}")
    lines.append(f"Recommendation: {RECOMMENDATIONS[snap.status]}")
    return "\n".join(lines)


__all__ = [
    "Snapshot", "config_dir", "data_dir", "state_dir", "find_transcript", "latest_transcript_for_cwd",
    "default_window", "from_statusline_payload", "read_transcript_usage", "resolve_snapshot",
    "load_state", "save_state", "latest_state", "iter_states", "prune_states", "write_json_atomic",
    "fmt_tokens", "render_statusline", "render_warning", "render_report", "quality_window",
]
