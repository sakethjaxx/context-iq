# 🧠 ContextIQ

> Know when your AI is losing its mind — before it does.

ContextIQ puts a live **intelligence score** in Claude Code's status line and warns you before a long session's answers start to slip.

```
🟢 IQ:100 fresh | 16k/1M ctx
🟡 IQ:58 warm | 300k/1M ctx
🟠 IQ:24 strained | 340k/1M ctx | /compact soon
```

**Free and open source. No API key, no pip installs, no per-turn tool calls.** Claude Code already measures the context window exactly; ContextIQ reads those numbers and turns them into a quality-aware score.

---

## Install (2 minutes)

You need Claude Code and Python 3.9+.

### Option A — plugin (recommended)

In Claude Code:

```
/plugin install context-iq --marketplace sakethjaxx/context-iq
```

On Claude Code older than 2.1.275, use two steps instead: `/plugin marketplace add sakethjaxx/context-iq`, then `/plugin install context-iq@context-iq`.

That gives you the early warnings and the health check. To also put the score in your status line, run this once:

```
/context-iq:setup-statusline
```

### Option B — one command, no plugin

```bash
git clone https://github.com/sakethjaxx/context-iq.git
python3 context-iq/install.py          # Windows: python context-iq\install.py
```

This adds the status line, the warning hook and the health check to `~/.claude/settings.json`. The file is backed up first, and your other settings are left alone. If you already have a status line, it's kept unless you pass `--force`. Preview the changes with `--dry-run`, and remove everything with `--uninstall`.

Start a new Claude Code session afterwards.

---

## What you get

| Feature | What it does |
|---|---|
| **Status line** | Live score after every reply, e.g. `🟠 IQ:24 strained \| 340k/1M ctx \| /compact soon` |
| **Early warnings** | One message when the session turns *strained*, another if it turns *critical*. Silent otherwise, and re-armed after `/compact` |
| **Ask anytime** | Say *"check my context health"* to get the score, tokens in context and what to do |
| **Live dashboard** | `python3 watch.py` in a second terminal (needs `pip install rich`) |

---

## How the score works

Answer quality drops non-linearly as context grows: it's fine for a long time, then it falls fast. The score is a logistic curve over *context pressure*:

| Score | Status | What to do |
|-------|--------|------------|
| 70–100 | 🟢 fresh | Keep going |
| 40–69 | 🟡 warm | `/compact` at the next natural break |
| 15–39 | 🟠 strained | `/compact` soon, or `/clear` when you switch tasks |
| 0–14 | 🔴 critical | `/compact` now, or `/clear` to start fresh |

**Pressure = tokens in context ÷ min(context window, quality horizon).** The quality horizon (default 400k tokens) matters for 1M-token models. Quality depends on how much is *in* context, not on how much room is left, so a 1M window shouldn't read "fresh" at 600k tokens. On 200k-window models the horizon has no effect. It's a heuristic, so tune it to taste (see below).

**Where the numbers come from:**
- The status line receives Claude Code's own `context_window` data on stdin.
- The warning hook and the health check read the latest reply's usage from the session transcript. That's the same input-token count Claude Code's `used_percentage` is based on.

Nothing is estimated, and nothing extra is sent to the model.

### Settings

Set these in your shell, or in the `env` block of `~/.claude/settings.json`:

| Variable | Default | Effect |
|---|---|---|
| `CONTEXT_IQ_QUALITY_WINDOW` | `400000` | Quality horizon in tokens. `200000` warns earlier on 1M models; `0` scores against the full window |
| `CONTEXT_IQ_WARN` | `strained` | When to warn: `warm`, `strained`, `critical` or `off` |
| `CONTEXT_IQ_DEBUG` | unset | `1` prints status line / hook errors to stderr |

---

## Upgrading from v2 (MCP server + CLAUDE.md tracking)

v2 asked Claude to call `track_turn` with its own token counts after every reply. Models can't see their token counts, so those numbers were guesses, and every call cost tokens. v3 reads the real numbers.

1. Delete the *ContextIQ — Auto Token Tracking* block from `~/.claude/CLAUDE.md`.
2. `git pull`, then `python3 install.py`. Your existing status line entry keeps working even before you rerun the installer.
3. The MCP server is optional now. Keep it with `python3 install.py --with-mcp`, or remove it with `claude mcp remove --scope user context-iq`.

---

## Platform support

| Where | Status line | Warnings | Health check |
|---|---|---|---|
| Claude Code in a terminal | ✅ | ✅ | ✅ |
| Claude Code IDE extensions | — | ✅ | ✅ |
| Other MCP clients (e.g. Claude Desktop chat) | — | — | MCP server, estimates only |

The custom status line is a terminal feature of Claude Code. Warnings and health checks use hooks and skills.

---

## Optional: MCP server

```bash
python3 install.py --with-mcp
```

This installs the `mcp` package (1.x and 2.x both work) and registers the server with Claude Code. It provides these tools:
- `get_context_pressure_score` and `get_session_stats`: exact numbers in Claude Code.
- `track_turn` and `reset_session`: model-reported estimates, for MCP clients that don't expose usage.

---

## Standalone chat (Groq free tier or Claude API)

A terminal chat with the meter built in, for any model.

```bash
pip install -r requirements.txt
cp .env.example .env      # add GROQ_API_KEY (free at console.groq.com) or ANTHROPIC_API_KEY
python3 main.py
```

| Command | What it does |
|---------|-------------|
| `/stats` | Token counts + intelligence meter |
| `/reset` | Clear history and counts |
| `/model` | Show active model |
| `/help` | Show all commands |
| `/quit` | Exit |

Pick the provider in `.env` (`PROVIDER=groq` or `PROVIDER=claude`, plus `GROQ_MODEL` / `ANTHROPIC_MODEL`). To add a provider, subclass `BaseProvider` in [providers.py](providers.py), add it to `get_provider()` and send a PR. `python3 demo.py` renders sample meter states without any API calls.

---

## Troubleshooting

- **Status line is blank.** Accept the workspace trust dialog, then test the script by hand:
  `echo '{"session_id":"t","context_window":{"context_window_size":200000,"current_usage":{"input_tokens":5000}}}' | python3 statusline.py`.
  `claude --debug` logs status line errors.
- **`python3` not found (Windows).** Plugin commands try `python3` and then `python`. The script install writes the full interpreter path, so it doesn't depend on `PATH`.
- **Window looks wrong for a gateway or custom model ID.** ContextIQ uses the window Claude Code reports. Fix the window in Claude Code (for example with `CLAUDE_CODE_MAX_CONTEXT_TOKENS`) and ContextIQ follows.

---

## Project structure

```
context-iq/
├── install.py           # one-command setup / --uninstall (stdlib only)
├── contextiq.py         # status line, Stop-hook warnings, health report
├── statusline.py        # status line entry point (kept for older settings)
├── claude_code.py       # reads Claude Code usage; per-session state
├── meter.py             # score curve, quality horizon, model windows
├── .claude-plugin/      # plugin + marketplace manifests
├── hooks/hooks.json     # plugin warning hook
├── skills/              # /context-iq:context-health, /context-iq:setup-statusline
├── mcp_server.py        # optional MCP server
├── watch.py             # live dashboard (rich)
├── main.py, chat.py, providers.py, display.py, demo.py   # standalone chat
└── tests/               # python3 -m unittest -v
```

## Development

```bash
python3 -m unittest -v
claude plugin validate .
```

## License

MIT — free to use, modify, and distribute.
