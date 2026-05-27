import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from chat import ChatSession

session = ChatSession()
app = Server("chat-token-usage")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_session_stats",
            description="Get current chat session token usage and statistics",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="get_context_pressure_score",
            description="Get context pressure score (0-100) showing session freshness",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="get_context_pressure",
            description="Get context window pressure as percentage with tokens remaining",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="send_message",
            description="Send message to Claude with token tracking",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to send"}
                },
                "required": ["message"],
            },
        ),
        types.Tool(
            name="reset_session",
            description="Reset chat session — clears history and token counts",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_session_stats":
        s = session.stats
        return [types.TextContent(type="text", text=json.dumps({
            "model": s.model,
            "turns": s.turns,
            "total_input_tokens": s.total_input_tokens,
            "total_output_tokens": s.total_output_tokens,
            "total_tokens": s.total_tokens,
            "cache_read_tokens": s.cache_read_tokens,
            "cache_creation_tokens": s.cache_creation_tokens,
            "context_window": s.context_window,
        }, indent=2))]

    elif name == "get_context_pressure_score":
        s = session.stats
        recommendations = {
            "fresh": "Session healthy. No action needed.",
            "warm": "Session warming. Monitor usage.",
            "strained": "High context pressure. Consider reset soon.",
            "critical": "Critical pressure. Reset strongly recommended.",
        }
        return [types.TextContent(type="text", text=json.dumps({
            "context_pressure_score": s.context_pressure_score,
            "raw_pressure": round(s.raw_pressure * 100, 1),
            "status": s.status,
            "recommendation": recommendations[s.status],
        }, indent=2))]

    elif name == "get_context_pressure":
        s = session.stats
        return [types.TextContent(type="text", text=json.dumps({
            "pressure_percent": round(s.context_pressure * 100, 2),
            "raw_pressure_percent": round(s.raw_pressure * 100, 2),
            "tokens_used": s.live_context_tokens,
            "context_window": s.context_window,
            "tokens_remaining": max(0, s.usable_window - s.live_context_tokens),
        }, indent=2))]

    elif name == "send_message":
        message = arguments.get("message", "")
        response = session.send(message)
        s = session.stats
        return [types.TextContent(type="text", text=json.dumps({
            "response": response,
            "tokens_this_session": {
                "input": s.total_input_tokens,
                "output": s.total_output_tokens,
                "total": s.total_tokens,
            },
            "context_pressure_score": s.context_pressure_score,
            "raw_pressure": round(s.raw_pressure * 100, 1),
            "status": s.status,
        }, indent=2))]

    elif name == "reset_session":
        session.reset()
        return [types.TextContent(type="text", text=json.dumps({
            "status": "reset",
            "message": "Session cleared. Token counts at zero.",
        }))]

    return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(run())
