import asyncio
import json
import os
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from meter import SessionStats

STATE_FILE = os.path.expanduser("~/.claude/context-iq-state.json")


def _write_state(stats: SessionStats):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "model": stats.model,
                "turns": stats.turns,
                "total_input_tokens": stats.total_input_tokens,
                "total_output_tokens": stats.total_output_tokens,
                "total_tokens": stats.total_tokens,
                "live_context_tokens": stats.live_context_tokens,
                "intelligence_score": stats.intelligence_score,
                "status": stats.status,
                "confidence": stats.confidence,
                "context_pressure": round(stats.context_pressure * 100, 1),
                "context_window_source": "known" if stats.context_window_known else "defaulted",
            }, f)
    except Exception:
        pass

# In-memory session — persists while server process runs
_stats = SessionStats(model="claude-sonnet-4-6")

app = Server("context-iq")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="track_turn",
            description=(
                "Call this after EVERY response to track token usage. "
                "Pass the input_tokens and output_tokens from this turn."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "input_tokens":          {"type": "integer", "description": "Input tokens this turn (excluding cache)"},
                    "output_tokens":         {"type": "integer", "description": "Output tokens this turn"},
                    "cache_read_tokens":     {"type": "integer", "description": "Cache read tokens (optional, Claude only)"},
                    "cache_creation_tokens": {"type": "integer", "description": "Cache creation tokens (optional, Claude only)"},
                    "model":                 {"type": "string",  "description": "Model name (optional)"},
                },
                "required": ["input_tokens", "output_tokens"],
            },
        ),
        types.Tool(
            name="get_intelligence_score",
            description="Get session intelligence score (0-100) and context pressure. Call when asked about session health.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="get_session_stats",
            description="Get full token usage stats for the current session.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="reset_session",
            description="Reset session token counts. Call when starting a new topic or after /clear.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    global _stats

    if name == "track_turn":
        model = arguments.get("model")
        if model:
            _stats.model = model
        cache_read     = arguments.get("cache_read_tokens", 0)
        cache_creation = arguments.get("cache_creation_tokens", 0)
        _stats.turns += 1
        _stats.total_input_tokens  += arguments["input_tokens"]
        _stats.total_output_tokens += arguments["output_tokens"]
        _stats.cache_read_tokens      += cache_read
        _stats.cache_creation_tokens  += cache_creation
        effective_input = arguments["input_tokens"] + cache_read + cache_creation
        _stats.update_live_context(effective_input + arguments["output_tokens"])

        _write_state(_stats)
        return [types.TextContent(type="text", text=json.dumps({
            "tracked": True,
            "turns": _stats.turns,
            "total_tokens": _stats.total_tokens,
            "live_context_tokens": _stats.live_context_tokens,
            "intelligence_score": _stats.intelligence_score,
            "status": _stats.status,
            "confidence": _stats.confidence,
        }))]

    elif name == "get_intelligence_score":
        recommendations = {
            "fresh":    "Session healthy. No action needed.",
            "warm":     "Session warming up. Monitor usage.",
            "strained": "High context pressure. Consider /clear soon.",
            "critical": "Critical pressure. Run /clear now.",
        }
        result = {
            "score":               _stats.intelligence_score,
            "status":              _stats.status,
            "confidence":          _stats.confidence,
            "context_used":        f"{_stats.context_pressure * 100:.1f}%",
            "live_context_tokens": _stats.live_context_tokens,
            "tokens_remaining":    max(0, _stats.usable_window - _stats.live_context_tokens),
            "context_window_source": "known" if _stats.context_window_known else "defaulted",
            "recommendation":      recommendations[_stats.status],
        }
        if _stats.confidence == "low":
            result["warning"] = "Sudden context drop detected — likely hidden compaction. Score may be optimistic."
        elif not _stats.context_window_known:
            result["warning"] = f"Unknown model '{_stats.model}'; context window defaulted to {_stats.context_window:,}. Score may be inaccurate."
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "get_session_stats":
        return [types.TextContent(type="text", text=json.dumps({
            "model":          _stats.model,
            "turns":          _stats.turns,
            "health": {
                "intelligence_score":  _stats.intelligence_score,
                "status":              _stats.status,
                "confidence":          _stats.confidence,
                "live_context_tokens": _stats.live_context_tokens,
                "context_used":        f"{_stats.context_pressure * 100:.1f}%",
                "tokens_remaining":    max(0, _stats.usable_window - _stats.live_context_tokens),
                "context_window_source": "known" if _stats.context_window_known else "defaulted",
            },
            "usage": {
                "total_input_tokens":  _stats.total_input_tokens,
                "total_output_tokens": _stats.total_output_tokens,
                "total_tokens":        _stats.total_tokens,
                "cache_read_tokens":   _stats.cache_read_tokens,
                "cache_creation_tokens": _stats.cache_creation_tokens,
            },
            "context_window": _stats.context_window,
        }, indent=2))]

    elif name == "reset_session":
        _stats = SessionStats(model=_stats.model)
        _write_state(_stats)
        return [types.TextContent(type="text", text=json.dumps({
            "reset": True,
            "message": "Session cleared. Token counts at zero.",
        }))]

    return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(run())
