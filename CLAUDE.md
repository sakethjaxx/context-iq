# ContextIQ — Project Instructions

ContextIQ is a context-health meter for AI sessions. Package code lives in
`contextiq/`; tests in `tests/`.

## Architecture rules

- `contextiq/statusline.py`, `meter.py`, and `state.py` must stay **stdlib-only** —
  the status line runs on every refresh and must start fast.
- Real measurement beats self-reporting: in Claude Code, token data comes from the
  statusline stdin payload. The MCP server (`mcp_server.py`) is a fallback for hosts
  without a status line and its numbers are model-estimated — keep that caveat in
  descriptions and docs.
- State files are per-session and written atomically via `state.write_state`.
  Never write shared state directly.

## Development

- Run tests with `pytest` before committing. Add tests for meter/statusline/state changes.
- New providers: subclass `BaseProvider` in `providers.py`, register in `PROVIDERS`.
- New models: add to `MODEL_CONTEXT_WINDOWS` in `meter.py` (prefix matching handles dated IDs).

## Session health (dogfooding)

If the ContextIQ MCP server is connected in this session, you may check health with
`get_context_pressure_score` when asked about "context health" or "intelligence score",
and call `reset_session` after `/clear`. Do not fabricate token counts for `track_turn`
in Claude Code — the status line already tracks exactly.
