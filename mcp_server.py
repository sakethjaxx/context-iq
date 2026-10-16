"""ContextIQ MCP server (optional).

Gives Claude a tool for "how healthy is my context?". In Claude Code the numbers
are exact: they come from the session transcript and the status line, so nothing
needs to call track_turn. Other MCP clients (e.g. Claude Desktop) don't expose
usage; there the score falls back to the model's own estimates sent via track_turn.

    claude mcp add --scope user context-iq -- python3 /path/to/context-iq/mcp_server.py

Works with the `mcp` package 1.x (FastMCP) and 2.x (MCPServer).
"""
from __future__ import annotations

import json
import os
import time

import claude_code as cc
from meter import RECOMMENDATIONS, SessionStats

FRESH_SECONDS = 6 * 3600
NOT_NEEDED = ("Not needed in Claude Code: ContextIQ reads exact usage from the session. "
              "Remove any CLAUDE.md instruction that calls track_turn after every reply.")

_estimate = SessionStats(model="unknown")


def claude_code_snapshot(cwd: str = None):
    """Exact snapshot of the latest Claude Code session in this project, if any."""
    cwd = cwd or os.getcwd()
    state = cc.latest_state(cwd=cwd, max_age=FRESH_SECONDS)
    sid = state["session_id"] if state else None
    if not sid:
        transcript = cc.latest_transcript_for_cwd(cwd)
        if transcript and time.time() - os.path.getmtime(transcript) < FRESH_SECONDS:
            sid = os.path.splitext(os.path.basename(transcript))[0]
    return cc.resolve_snapshot(sid, cwd=cwd) if sid else None


def _exact_health(snap: cc.Snapshot) -> dict:
    if not snap.has_usage:
        return {"source": "claude-code", "status": "unknown",
                "message": "Conversation just compacted; usage refreshes after the next reply."}
    return {
        "source": "claude-code (exact)",
        "context_pressure_score": snap.score,
        "status": snap.status,
        "live_context_tokens": snap.used_tokens,
        "context_window": snap.window,
        "context_used": f"{snap.window_pct:.1f}%",
        "quality_horizon": snap.scored_window,
        "pressure": f"{100 * snap.pressure:.1f}%",
        "tokens_remaining": max(0, snap.window - snap.used_tokens),
        "model": snap.model,
        "session_id": snap.session_id,
        "recommendation": RECOMMENDATIONS[snap.status],
    }


def _estimated_health() -> dict:
    s = _estimate
    if not s.turns:
        return {"source": "none", "status": "unknown",
                "message": "No usage yet. In Claude Code this fills in after the first reply."}
    result = {
        "source": "estimated (track_turn)",
        "context_pressure_score": s.context_pressure_score,
        "raw_pressure": round(s.raw_pressure * 100, 1),
        "status": s.status,
        "confidence": s.confidence,
        "live_context_tokens": s.live_context_tokens,
        "context_window": s.context_window,
        "context_used": f"{s.context_pressure * 100:.1f}%",
        "tokens_remaining": max(0, s.usable_window - s.live_context_tokens),
        "model": s.model,
        "recommendation": RECOMMENDATIONS[s.status],
        "warning": "Model-reported estimates; treat the score as approximate.",
    }
    if s.confidence == "low":
        result["warning"] = "Sudden context drop detected (likely compaction). Score may be optimistic."
    return result


def context_health() -> dict:
    snap = claude_code_snapshot()
    return _exact_health(snap) if snap else _estimated_health()


def session_stats() -> dict:
    snap = claude_code_snapshot()
    if snap:
        return {"health": _exact_health(snap), "last_reply_output_tokens": snap.output_tokens,
                "window_source": snap.window_source, "cwd": snap.cwd}
    s = _estimate
    return {
        "health": _estimated_health(),
        "turns": s.turns,
        "usage": {
            "total_input_tokens": s.total_input_tokens,
            "total_output_tokens": s.total_output_tokens,
            "total_tokens": s.total_tokens,
            "cache_read_tokens": s.cache_read_tokens,
            "cache_creation_tokens": s.cache_creation_tokens,
        },
    }


def track_turn(input_tokens: int, output_tokens: int, cache_read_tokens: int = 0,
               cache_creation_tokens: int = 0, model: str = "") -> dict:
    if claude_code_snapshot():
        return {"tracked": False, "note": NOT_NEEDED}
    if model:
        _estimate.model = model
    _estimate.turns += 1
    _estimate.total_input_tokens += input_tokens
    _estimate.total_output_tokens += output_tokens
    _estimate.cache_read_tokens += cache_read_tokens
    _estimate.cache_creation_tokens += cache_creation_tokens
    _estimate.update_live_context(input_tokens + cache_read_tokens + cache_creation_tokens + output_tokens)
    return {"tracked": True, "turns": _estimate.turns,
            "context_pressure_score": _estimate.context_pressure_score, "status": _estimate.status}


def reset_session() -> dict:
    global _estimate
    _estimate = SessionStats(model=_estimate.model)
    return {"reset": True, "message": "Estimates cleared. (In Claude Code, /clear starts a new session automatically.)"}


def build_server():
    try:
        from mcp.server.mcpserver import MCPServer as Server   # mcp >= 2
    except ImportError:
        from mcp.server.fastmcp import FastMCP as Server       # mcp 1.x
    server = Server("context-iq")

    @server.tool(name="get_context_pressure_score",
                 description="ContextIQ health for this session: score 0-100, status (fresh/warm/strained/"
                             "critical), tokens in context and a recommendation. Call when the user asks "
                             "about context, session health or the intelligence score.")
    def _health() -> str:
        return json.dumps(context_health(), indent=2)

    @server.tool(name="get_session_stats", description="Detailed ContextIQ token stats for this session.")
    def _stats() -> str:
        return json.dumps(session_stats(), indent=2)

    @server.tool(name="track_turn",
                 description="Only for MCP clients that don't expose token usage (not Claude Code): record "
                             "your estimated tokens for the last turn. Claude Code usage is read automatically.")
    def _track(input_tokens: int, output_tokens: int, cache_read_tokens: int = 0,
               cache_creation_tokens: int = 0, model: str = "") -> str:
        return json.dumps(track_turn(input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, model))

    @server.tool(name="reset_session", description="Clear estimates recorded with track_turn.")
    def _reset() -> str:
        return json.dumps(reset_session())

    return server


if __name__ == "__main__":
    build_server().run()
