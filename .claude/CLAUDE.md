# ContextIQ: developer notes

ContextIQ turns the context usage Claude Code already measures into a 0-100
"intelligence score", a status line, and early warnings. It never asks the model
to report its own token counts.

## Layout

- `meter.py`: score curve, quality horizon, model windows, `SessionStats` (standalone chat)
- `claude_code.py`: reads usage from the status line payload and transcripts; per-session state in `~/.claude/context-iq/sessions/`
- `contextiq.py`: CLI with `statusline`, `hook` (Stop hook) and `health` subcommands
- `statusline.py`: back-compat shim for settings written by older versions
- `install.py`: edits `~/.claude/settings.json` (backup, idempotent, `--uninstall`)
- `.claude-plugin/`, `hooks/hooks.json`, `skills/`: Claude Code plugin packaging
- `mcp_server.py`: optional MCP server (mcp 1.x and 2.x); `watch.py`: rich dashboard
- `main.py`, `chat.py`, `providers.py`, `display.py`: standalone chat (Groq / Claude API)

## Rules

- `meter.py`, `claude_code.py`, `contextiq.py`, `statusline.py` and `install.py` must stay
  standard-library only and run on Python 3.9+ (macOS, Linux, Windows).
- The `statusline` and `hook` commands must never raise or exit non-zero; a failure
  there degrades Claude Code itself.
- Keep tests isolated by pointing `CLAUDE_CONFIG_DIR` at a temp dir.

## Checks

```bash
python3 -m unittest -v
claude plugin validate .
```
