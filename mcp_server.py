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
                "input_tokens": stats.input_tokens,
                "output_tokens": stats.output_tokens,
                "total_tokens": stats.total_tokens,
                "intelligence_score": stats.intelligence_score,
                "status": stats.status,
                "context_pressure": round(stats.context_pressure * 100, 1),
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
                    "input_tokens":  {"type": "integer", "description": "Input tokens this turn"},
                    "output_tokens": {"type": "integer", "description": "Output tokens this turn"},
                    "model":         {"type": "string",  "description": "Model name (optional)"},
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
        _stats.turns += 1
        _stats.input_tokens += arguments["input_tokens"]
        _stats.output_tokens += arguments["output_tokens"]

        _write_state(_stats)
        return [types.TextContent(type="text", text=json.dumps({
            "tracked": True,
            "turns": _stats.turns,
            "total_tokens": _stats.total_tokens,
            "intelligence_score": _stats.intelligence_score,
            "status": _stats.status,
        }))]

    elif name == "get_intelligence_score":
        recommendations = {
            "fresh":    "Session healthy. No action needed.",
            "warm":     "Session warming up. Monitor usage.",
            "strained": "High context pressure. Consider /clear soon.",
            "critical": "Critical pressure. Run /clear now.",
        }
        return [types.TextContent(type="text", text=json.dumps({
            "score":          _stats.intelligence_score,
            "status":         _stats.status,
            "context_used":   f"{_stats.context_pressure * 100:.1f}%",
            "tokens_remaining": _stats.context_window - _stats.input_tokens,
            "recommendation": recommendations[_stats.status],
        }, indent=2))]

    elif name == "get_session_stats":
        return [types.TextContent(type="text", text=json.dumps({
            "model":         _stats.model,
            "turns":         _stats.turns,
            "input_tokens":  _stats.input_tokens,
            "output_tokens": _stats.output_tokens,
            "total_tokens":  _stats.total_tokens,
            "context_window": _stats.context_window,
            "context_used":  f"{_stats.context_pressure * 100:.1f}%",
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
