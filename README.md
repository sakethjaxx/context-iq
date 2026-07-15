# 🧠 ContextIQ

> Know when your AI is losing its mind — before it does.

ContextIQ shows a live **context-health meter** for your AI sessions. As the context window fills up, response quality silently degrades. ContextIQ makes that visible — in your Claude Code status line, a live terminal dashboard, or a standalone chat.

**Free. Open source. Measures real token counts — it never asks the model to guess.**

```
🟢 IQ:96 | 15.2k/200k ctx (8%) | $0.01      ← live status line in Claude Code
```

---

## How it works

Claude Code pipes exact session data (token usage, context window size, cost) to status line scripts on stdin. ContextIQ reads that, runs it through a logistic pressure curve, and prints one line. No API key, no MCP tool calls, no self-reported numbers, near-zero overhead (stdlib-only).

Quality degrades non-linearly — fine until ~50% full, then drops fast:

| Score | Status | What to do |
|-------|--------|------------|
| 70–100 | 🟢 FRESH | Keep going |
| 40–69 | 🟡 WARM | Monitor usage |
| 15–39 | 🟠 STRAINED | Consider `/clear` soon |
| 0–14 | 🔴 CRITICAL | `/clear` now |

---

## Quick start — Claude Code (recommended)

```bash
pip install git+https://github.com/sakethjaxx/context-iq.git
contextiq-setup
```

The setup wizard adds the status line to `~/.claude/settings.json` (with your confirmation, backing up the file first). Restart Claude Code and the meter appears after the first response.

Prefer to configure manually? Add this to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python -m contextiq.statusline"
  }
}
```

> Use the full path to your Python if it isn't on Claude Code's PATH (e.g. `"C:/Users/you/AppData/Local/Programs/Python/Python312/python.exe -m contextiq.statusline"` on Windows — forward slashes work best there).

That's it. **No CLAUDE.md instructions, no MCP server, no API key needed** — Claude Code supplies exact counts.

### Live dashboard (optional)

Run a full-size meter in a second terminal:

```bash
pip install "contextiq[watch] @ git+https://github.com/sakethjaxx/context-iq.git"
contextiq-watch                 # follows the most recent session
contextiq-watch <session_id>    # follows one session
```

Multiple concurrent sessions each get their own state file under `~/.claude/context-iq/` — they never clobber each other.

---

## Claude Desktop / hosts without a status line (MCP fallback)

Claude Desktop has no status line, so ContextIQ ships an MCP server the model can report into:

```bash
pip install "contextiq[mcp] @ git+https://github.com/sakethjaxx/context-iq.git"
claude mcp add -s user context-iq python -- -m contextiq.mcp_server
```

Then add to your global `CLAUDE.md` (or Desktop instructions):

```markdown
# ContextIQ — Token Tracking

After EVERY response, call the `track_turn` MCP tool (server: context-iq) with your
estimated `input_tokens`, `output_tokens`, and `model`.

When asked about "context health", "session health", or "context pressure" — call
`get_context_pressure_score` and show the result.

When the session is cleared or reset — call `reset_session`.
```

> ⚠️ **Accuracy caveat:** models can't see their real token counts, so MCP-path numbers are estimates. The score is directional, not exact. In Claude Code, always prefer the status line — it's measured, not guessed.

Tools exposed: `track_turn`, `get_context_pressure_score`, `get_session_stats`, `reset_session`.

---

## Standalone chat (any terminal, bring a key)

Works with Groq (free tier), Claude, OpenAI, or any OpenAI-compatible endpoint (Ollama, LM Studio, OpenRouter, vLLM).

```bash
git clone https://github.com/sakethjaxx/context-iq.git
cd context-iq
pip install -e ".[chat]"
cp .env.example .env      # add your key
contextiq
```

Provider examples for `.env`:

```env
# Groq — free tier, no credit card (console.groq.com)
PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# Claude (console.anthropic.com)
PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6

# Local models via Ollama — completely free & offline
PROVIDER=ollama
OPENAI_MODEL=llama3.2

# OpenAI or any compatible endpoint (LM Studio, OpenRouter, vLLM...)
PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=          # optional, defaults to api.openai.com
OPENAI_MODEL=gpt-4o-mini
```

In-chat commands: `/stats`, `/reset`, `/model`, `/help`, `/quit`.

---

## What the score means (and doesn't)

- **Context pressure** = live context tokens ÷ usable window (window minus a response reserve). Real, measured.
- **Score (0–100)** = a logistic curve over pressure: flat plateau until ~40%, noticeable decline 40–70%, steep 70–90%, cliff past 90%. The *shape* reflects how long-context degradation is commonly experienced, but the score is a **heuristic**, not a benchmark of your model's actual accuracy.
- **Confidence** drops to `low` when live context suddenly shrinks >30% — usually hidden auto-compaction, which means earlier detail may already be lost.
- Unknown models fall back to a 128k window (`confidence: medium`). Force a window with `CONTEXTIQ_CONTEXT_WINDOW=1000000`. Dated model IDs (`claude-haiku-4-5-20251001`) resolve by prefix automatically.

---

## Project structure

```
contextiq/
├── meter.py        # pressure → score curve, model window table
├── statusline.py   # Claude Code status line (stdlib-only, reads stdin JSON)
├── state.py        # per-session atomic state files (~/.claude/context-iq/)
├── watch.py        # live Rich dashboard  (contextiq-watch)
├── mcp_server.py   # MCP fallback server (contextiq-mcp)
├── providers.py    # Groq / Claude / OpenAI-compatible providers
├── chat.py, cli.py, display.py   # standalone chat (contextiq)
└── install.py      # setup wizard      (contextiq-setup)
tests/              # pytest suite (runs in CI on Linux + Windows, py3.9–3.13)
```

## Contributing

```bash
pip install -e ".[dev]"
pytest
```

Add a provider by subclassing `BaseProvider` in `providers.py` and registering it in `PROVIDERS`. Add a model's context window to `MODEL_CONTEXT_WINDOWS` in `meter.py`. PRs welcome.

## License

MIT — free to use, modify, and distribute.
