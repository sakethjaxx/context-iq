# ContextIQ — Auto Tracking

After EVERY response you give, call the `track_turn` MCP tool with:
- `input_tokens`: your input token count for this turn
- `output_tokens`: your output token count for this turn
- `model`: your model name

When the user asks anything like "check context", "session health", "how fresh are you", or "intelligence score" — call `get_intelligence_score` and show the result clearly.

When the user runs `/clear` or says "reset session" — call `reset_session`.
