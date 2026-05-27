# 🧠 ContextIQ

> Know when your AI is losing its mind — before it does.

ContextIQ tracks token usage and shows a live **Intelligence Meter** for your AI sessions. As context fills up, response quality silently degrades. ContextIQ makes that visible.

**Free. Open source. No paid API required.**

---

## How it works

```
🟢 IQ:83 | 12,450tok | 4turns          ← live status bar in Claude Code
```

- Tracks tokens every turn automatically
- Intelligence score (0–100) shows context pressure
- Warns before your session gets dumb
- Works as standalone chat OR plugged into Claude Code / Desktop

---

## Modes

| Mode | Best for | API key needed? |
|------|---------|-----------------|
| **MCP server** | Claude Code CLI, Claude Desktop, VSCode | No |
| **Standalone chat** | Anyone, any terminal | Yes (Groq, free) |

---

## Option A — MCP Server (recommended, no API key)

Works with your existing Claude subscription.

### 1. Clone & run setup

```bash
git clone https://github.com/sakethjaxx/context-iq.git
cd context-iq
pip install -r requirements.txt
python setup.py
```

`setup.py` registers the MCP server automatically and prints the two manual steps below.

### 2. Add to `~/.claude/settings.json`

Open `~/.claude/settings.json` and add:

```json
{
  "permissions": {
    "allow": ["mcp__context-iq__*"]
  },
  "statusLine": {
    "type": "command",
    "command": "python /path/to/context-iq/statusline.py",
    "refreshInterval": 10
  }
}
```

> **Windows path example:** `"python C:\\Users\\you\\context-iq\\statusline.py"`

### 3. Add to `~/.claude/CLAUDE.md`

Create `~/.claude/CLAUDE.md` (or append to existing) and add:

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

### 4. Restart Claude Code

Status bar appears:
```
🟢 IQ:100 | 0tok | 0turns
```

### 5. Ask anytime

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

## Option B — Standalone Chat (Groq, free tier)

### 1. Clone & install

```bash
git clone https://github.com/sakethjaxx/context-iq.git
cd context-iq
pip install -r requirements.txt
```

### 2. Get a free Groq API key

1. Sign up at [console.groq.com](https://console.groq.com) — no credit card
2. **API Keys** → **Create API Key** → copy it

### 3. Configure

```bash
cp .env.example .env
```

Open `.env`:
```env
PROVIDER=groq
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

### 4. Run

```bash
python main.py
```

---

## What you see (standalone chat)

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
| `/stats` | Token counts + intelligence meter |
| `/reset` | Clear history, reset count |
| `/model` | Show active model |
| `/help` | Show all commands |
| `/quit` | Exit |

---

## Intelligence Meter explained

Quality degrades non-linearly — fine until ~50% full, then drops fast.

| Score | Status | What to do |
|-------|--------|------------|
| 70–100 | 🟢 FRESH | Keep going |
| 40–69 | 🟡 WARM | Monitor usage |
| 15–39 | 🟠 STRAINED | Consider `/reset` or `/clear` |
| 0–14 | 🔴 CRITICAL | Reset now |

---

## Platform support

| Platform | Auto tracking | Live status bar | On-demand check |
|----------|--------------|-----------------|-----------------|
| Claude Code CLI | ✅ | ✅ | ✅ |
| Claude Desktop | ✅ | ❌ | ✅ |
| VSCode extension | ✅ | ❌ | ✅ |

The status bar is a Claude Code CLI feature. Desktop and VSCode support tracking and on-demand checks via MCP tools.

---

## Supported models

### Groq (free)

| Model | Context | Best for |
|-------|---------|----------|
| `llama-3.3-70b-versatile` | 128k | Best quality (default) |
| `llama-3.1-8b-instant` | 131k | Fastest |
| `mixtral-8x7b-32768` | 32k | Balanced |

### Claude (BYOK — standalone chat only)

```env
PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-your_key_here
ANTHROPIC_MODEL=claude-sonnet-4-6
```

New? [console.anthropic.com](https://console.anthropic.com) — free $5 credits on signup.

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
├── setup.py         # one-command setup for new users
├── main.py          # standalone chat loop
├── chat.py          # ChatSession wrapper
├── providers.py     # GroqProvider, ClaudeProvider, BaseProvider
├── meter.py         # intelligence score algorithm
├── display.py       # rich terminal UI
├── mcp_server.py    # MCP server (no API key needed)
├── statusline.py    # status bar script for Claude Code
├── CLAUDE.md        # copy to ~/.claude/CLAUDE.md for auto-tracking
├── requirements.txt
├── .env.example
└── LICENSE          # MIT
```

---

## License

MIT — free to use, modify, and distribute.
