"""Claude Code status line.

Claude Code pipes a JSON payload to this script on stdin containing the
session's *real* token usage (``context_window.current_usage``) and window
size — no API key, no MCP tool, no self-reported numbers. We score it and
print one line. When the payload lacks context data (older Claude Code
versions, or manual runs) we fall back to state written by the MCP server.

Stdlib-only on purpose: this runs on every statusline refresh, so startup
must stay fast.
"""
import json
import sys

from .meter import SessionStats
from .state import read_state, write_state

ICONS = {
    "fresh": ("\U0001F7E2", "OK"),
    "warm": ("\U0001F7E1", "WARN"),
    "strained": ("\U0001F7E0", "HIGH"),
    "critical": ("\U0001F534", "CRIT"),
}


def _fmt_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def stats_from_payload(payload: dict) -> "SessionStats | None":
    """Build SessionStats from a Claude Code statusline stdin payload."""
    cw = payload.get("context_window") or {}
    usage = cw.get("current_usage") or {}
    model = (payload.get("model") or {}).get("id") or "unknown"
    window = cw.get("context_window_size") or 0

    live = 0
    if usage:
        live = sum(
            int(usage.get(k) or 0)
            for k in ("input_tokens", "output_tokens",
                      "cache_creation_input_tokens", "cache_read_input_tokens")
        )
    if live == 0 and cw.get("used_percentage") and window:
        live = int(window * float(cw["used_percentage"]) / 100)
    if live == 0 and not usage:
        return None

    stats = SessionStats(
        model=model,
        total_input_tokens=int(cw.get("total_input_tokens") or 0),
        total_output_tokens=int(cw.get("total_output_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        context_window_override=int(window),
    )
    stats.update_live_context(live)
    return stats


def render_line(stats: SessionStats, cost_usd: "float | None" = None,
                ascii_only: bool = False) -> str:
    icon, ascii_icon = ICONS[stats.status]
    parts = [
        f"{ascii_icon if ascii_only else icon} IQ:{stats.context_pressure_score:.0f}",
        f"{_fmt_tokens(stats.live_context_tokens)}/{stats.context_window // 1000}k ctx ({stats.raw_pressure * 100:.0f}%)",
    ]
    if cost_usd:
        parts.append(f"${cost_usd:.2f}")
    return " | ".join(parts)


def render_from_state(state: dict, ascii_only: bool = False) -> str:
    """Fallback: render from MCP-written state (Claude Desktop etc.)."""
    if not state:
        return "ContextIQ ready" if ascii_only else "\U0001F9E0 ContextIQ ready"
    status = state.get("status", "fresh")
    icon, ascii_icon = ICONS.get(status, ICONS["fresh"])
    score = state.get("context_pressure_score", 100)
    tokens = state.get("live_context_tokens", state.get("total_tokens", 0))
    turns = state.get("turns", 0)
    return (f"{ascii_icon if ascii_only else icon} IQ:{score:.0f} | "
            f"{_fmt_tokens(tokens)} ctx | {turns}turns")


def build_output(raw_stdin: str) -> str:
    try:
        payload = json.loads(raw_stdin) if raw_stdin.strip() else {}
    except ValueError:
        payload = {}

    stats = stats_from_payload(payload) if payload else None
    if stats is not None:
        cost = (payload.get("cost") or {}).get("total_cost_usd")
        session_id = payload.get("session_id")
        write_state({
            "source": "claude-code",
            "model": stats.model,
            "live_context_tokens": stats.live_context_tokens,
            "total_input_tokens": stats.total_input_tokens,
            "total_output_tokens": stats.total_output_tokens,
            "total_tokens": stats.total_tokens,
            "context_window": stats.context_window,
            "context_pressure_score": stats.context_pressure_score,
            "raw_pressure": round(stats.raw_pressure * 100, 1),
            "status": stats.status,
            "confidence": stats.confidence,
            "cost_usd": cost,
        }, session_id=session_id)
        return render_line(stats, cost_usd=cost)

    return render_from_state(read_state(
        (payload.get("session_id") if payload else None)))


def main() -> None:
    raw = "" if sys.stdin.isatty() else sys.stdin.read()
    line = build_output(raw)
    try:
        print(line, end="")
    except UnicodeEncodeError:
        # Rebuild without emoji for terminals stuck on a legacy codepage
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except ValueError:
            payload = {}
        stats = stats_from_payload(payload) if payload else None
        if stats is not None:
            print(render_line(stats, cost_usd=(payload.get("cost") or {}).get("total_cost_usd"),
                              ascii_only=True), end="")
        else:
            print(render_from_state(read_state(None), ascii_only=True), end="")


if __name__ == "__main__":
    main()
