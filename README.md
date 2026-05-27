# 🧠 ContextIQ

> Know when your AI is losing its mind — before it does.

ContextIQ tracks token usage and shows a live **Intelligence Meter** for your chat sessions. As context fills up, AI responses get worse. ContextIQ tells you exactly how close you are to that cliff.

**Free to use. Works with Groq (free tier) out of the box. Claude optional.**

---

## What it looks like

```
You> explain quantum entanglement

╭─ Assistant ──────────────────────────────────────────────────────╮
│ Quantum entanglement is a phenomenon where two particles become  │
│ correlated such that the quantum state of each particle cannot   │
│ be described independently...                                    │
╰──────────────────────────────────────────────────────────────────╯

╭─ Session Stats ──────╮   ╭─ Intelligence Meter ─────────────────────────────╮
│ Model   llama-3.3-70b│   │ Intelligence Score                               │
│ Turns   4            │   │ ████████████████████████░░░░░░░░░░░░ 83/100 FRESH│
│ Input   12,450       │   │                                                  │
│ Output  3,821        │   │ Context Pressure                                 │
│ Total   16,271       │   │ ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 9.7% of 128k│
╰──────────────────────╯   ╰──────────────────────────────────────────────────╯
```

---

## Install in 3 steps

### Step 1 — Clone the repo

```bash
git clone https://github.com/your-username/context-iq.git
cd context-iq
```

### Step 2 — Install Python packages

```bash
pip install -r requirements.txt
```

> Requires Python 3.9+. Check with `python --version`.

### Step 3 — Add your free API key

```bash
cp .env.example .env
```

Open `.env` and paste your Groq key (see below for how to get one — it's free).

---

## Getting a free Groq API key

Groq runs powerful AI models for free. No credit card needed.

1. Go to **[console.groq.com](https://console.groq.com)** and create a free account
2. Click **API Keys** in the left sidebar
3. Click **Create API Key**, copy it
4. Open your `.env` file and replace `gsk_your_key_here` with your key

That's it. Run `python main.py` and start chatting.

---

## Run it

```bash
python main.py
```

To use a specific model:

```bash
python main.py llama-3.1-8b-instant
```

---

## Commands

Type these during a chat session:

| Command | What it does |
|---------|-------------|
| `/stats` | Show token counts + intelligence meter |
| `/reset` | Start fresh — clears history and resets token count |
| `/model` | Show which model you're using |
| `/help` | Show all commands |
| `/quit` | Exit |

---

## Intelligence Meter — what the score means

The score shows how much of the AI's memory (context window) your session has consumed. The more filled it is, the worse responses get.

| Score | Status | What to do |
|-------|--------|------------|
| 70–100 | 🟢 FRESH | You're good |
| 40–69 | 🟡 WARM | Keep an eye on it |
| 15–39 | 🟠 STRAINED | Think about `/reset` |
| 0–14 | 🔴 CRITICAL | Reset now |

ContextIQ warns you automatically when things get strained.

---

## Use Claude instead of Groq (optional)

If you have a Claude API key, swap two lines in `.env`:

```env
PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-your_key_here
ANTHROPIC_MODEL=claude-sonnet-4-6
```

New to Claude? Sign up at [console.anthropic.com](https://console.anthropic.com) — free $5 credits on signup.

---

## Use as an MCP tool (Claude Code / Claude Desktop)

ContextIQ can run as an MCP server so Claude itself can check your session health.

Add this to your MCP config:

**Claude Code** (`~/.claude/settings.json`):
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

**Claude Desktop** (`claude_desktop_config.json`):
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

MCP tools available: `get_session_stats`, `get_intelligence_score`, `get_context_pressure`, `send_message`, `reset_session`

---

## Supported models

### Groq (free)

| Model | Context window | Best for |
|-------|---------------|----------|
| `llama-3.3-70b-versatile` | 128k | Best quality (default) |
| `llama-3.1-8b-instant` | 131k | Fastest responses |
| `mixtral-8x7b-32768` | 32k | Balanced |

### Claude (BYOK)

| Model | Context window |
|-------|---------------|
| `claude-sonnet-4-6` | 200k |
| `claude-opus-4-7` | 200k |
| `claude-haiku-4-5` | 200k |

---

## Add a new provider

Implement `BaseProvider` in [providers.py](providers.py):

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

Then wire it up in `get_provider()` and add `"openai"` to the `PROVIDER` options.

PRs welcome.

---

## Project structure

```
context-iq/
├── main.py          # chat loop + commands
├── chat.py          # session wrapper
├── providers.py     # Groq, Claude (swappable)
├── meter.py         # intelligence score algorithm
├── display.py       # terminal UI (rich)
├── mcp_server.py    # MCP server
├── requirements.txt
├── .env.example
└── LICENSE          # MIT
```

---

## License

MIT — free to use, modify, and distribute.
