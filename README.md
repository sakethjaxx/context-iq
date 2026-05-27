# 🧠 ContextIQ

> Know when your AI is losing its mind — before it does.

ContextIQ tracks token usage and shows a live **Intelligence Meter** for your AI sessions. As context fills up, response quality silently degrades. ContextIQ makes that visible.

**Free. Open source. Two modes — pick one or use both.**

---

## Modes

| Mode | What it does | Needs API key? |
|------|-------------|----------------|
| **Standalone chat** | Terminal UI with live meter, powered by Groq | Yes (free) |
| **MCP server** | Plugs into Claude Code / Claude Desktop | No |

---

## Quick start — MCP Server (Claude Code / Claude Desktop)

If you already use Claude Code or Claude Desktop, this is the zero-cost path.

### Step 1 — Clone & install

```bash
git clone https://github.com/sakethjaxx/context-iq.git
cd context-iq
pip install -r requirements.txt
```

### Step 2 — Register the MCP server

**Claude Code CLI:**
```bash
claude mcp add -s user context-iq python "/path/to/context-iq/mcp_server.py"
```

**Claude Desktop** — add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "context-iq": {
      "command": "python",
      "args": ["/path/to/context-iq/mcp_server.py"]
    }
  }
}
```

### Step 3 — Enable auto-tracking

Add this to your global `~/.claude/CLAUDE.md` (create the file if it doesn't exist):

```markdown
# ContextIQ — Auto Token Tracking

After EVERY response you give, call the `context-iq__track_turn` MCP tool with:
- `input_tokens`: your input token count for this turn
- `output_tokens`: your output token count for this turn
- `model`: your model name

When the user asks "check context", "session health", or "intelligence score" — call
`context-iq__get_intelligence_score` and show the result.

When the user runs /clear or says "reset session" — call `context-iq__reset_session`.
```

### Step 4 — Restart Claude Code

### Step 5 — Ask Claude anytime:

```
check my context health
```

```
what's my intelligence score
```

```
session stats
```

---

## Quick start — Standalone Chat (Groq, free)

### Step 1 — Clone & install

```bash
git clone https://github.com/sakethjaxx/context-iq.git
cd context-iq
pip install -r requirements.txt
```

### Step 2 — Get a free Groq API key

1. Sign up at [console.groq.com](https://console.groq.com) — no credit card needed
2. Go to **API Keys** → **Create API Key** → copy it

### Step 3 — Configure

```bash
cp .env.example .env
```

Open `.env` and paste your key:

```env
PROVIDER=groq
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

### Step 4 — Run

```bash
python main.py
```

---

## What you see

```
ContextIQ  model: llama-3.3-70b-versatile
Type /help for commands.

You> explain black holes

╭─ Assistant ─────────────────────────────────────────────────╮
│ A black hole is a region of spacetime where gravity is so   │
│ strong that nothing — not even light — can escape...        │
╰─────────────────────────────────────────────────────────────╯

╭─ Session Stats ──────╮  ╭─ Intelligence Meter ──────────────────────────────╮
│ Model   llama-3.3-70b│  │ Intelligence Score                                │
│ Turns   3            │  │ ████████████████████████░░░░░░░░░░░░ 83/100 FRESH  │
│ Input   9,240        │  │                                                   │
│ Output  2,105        │  │ Context Pressure                                  │
│ Total   11,345       │  │ ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 7.2% of 128k │
╰──────────────────────╯  ╰───────────────────────────────────────────────────╯
```

### Commands

| Command | What it does |
|---------|-------------|
| `/stats` | Show token counts + intelligence meter |
| `/reset` | Clear history, reset token count |
| `/model` | Show active model |
| `/help` | Show all commands |
| `/quit` | Exit |

---

## Intelligence Meter

Context degrades non-linearly — it feels fine until ~50% full, then quality drops fast.

| Score | Status | What to do |
|-------|--------|------------|
| 70–100 | 🟢 FRESH | Keep going |
| 40–69 | 🟡 WARM | Monitor usage |
| 15–39 | 🟠 STRAINED | Think about `/reset` or `/clear` |
| 0–14 | 🔴 CRITICAL | Reset now |

---

## Supported models

### Groq (free)

| Model | Context window | Best for |
|-------|---------------|----------|
| `llama-3.3-70b-versatile` | 128k | Best quality (default) |
| `llama-3.1-8b-instant` | 131k | Fastest |
| `mixtral-8x7b-32768` | 32k | Balanced |

### Claude (BYOK)

Update `.env`:
```env
PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-your_key_here
ANTHROPIC_MODEL=claude-sonnet-4-6
```

New? Sign up at [console.anthropic.com](https://console.anthropic.com) — free $5 credits on signup.

---

## Add a new provider

Subclass `BaseProvider` in [providers.py](providers.py):

```python
class OpenAIProvider(BaseProvider):
    def __init__(self, api_key=None, model=None):
        from openai import OpenAI
        self._model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    @property
    def model_id(self) -> str:
        return self._model

    def send(self, messages, system) -> ProviderResponse:
        full_messages = [{"role": "system", "content": system}] + messages
        res = self._client.chat.completions.create(
            model=self._model, messages=full_messages, max_tokens=8096
        )
        return ProviderResponse(
            text=res.choices[0].message.content,
            input_tokens=res.usage.prompt_tokens,
            output_tokens=res.usage.completion_tokens,
        )
```

Add it to `get_provider()` and send a PR.

---

## Project structure

```
context-iq/
├── main.py          # standalone chat loop
├── chat.py          # ChatSession wrapper
├── providers.py     # GroqProvider, ClaudeProvider, BaseProvider
├── meter.py         # intelligence score algorithm
├── display.py       # rich terminal UI
├── mcp_server.py    # MCP server (no API key needed)
├── CLAUDE.md        # copy this to ~/.claude/CLAUDE.md for auto-tracking
├── requirements.txt
├── .env.example
└── LICENSE          # MIT
```

---

## License

MIT — free to use, modify, and distribute.
