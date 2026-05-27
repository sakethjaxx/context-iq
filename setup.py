"""
ContextIQ setup script.
Run once after cloning: python setup.py
"""
import os
import subprocess
import sys
import platform
import io

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.abspath(os.path.dirname(__file__))
MCP_SCRIPT = os.path.join(HERE, "mcp_server.py")
STATUSLINE_SCRIPT = os.path.join(HERE, "statusline.py")
PYTHON = sys.executable
IS_WIN = platform.system() == "Windows"
SEP = "\\" if IS_WIN else "/"


def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


def ok(msg):  print(f"  ✅ {msg}")
def warn(msg): print(f"  ⚠️  {msg}")
def info(msg): print(f"  ℹ️  {msg}")
def step(msg): print(f"\n  👉 {msg}")


print("\n🧠 ContextIQ Setup\n")

# ── Step 1: Install dependencies ──────────────────────────────────
section("1/4  Installing dependencies")
code, out, err = run(f'"{PYTHON}" -m pip install -r requirements.txt -q')
if code == 0:
    ok("Dependencies installed")
else:
    warn(f"pip install failed: {err}")
    warn("Run manually: pip install -r requirements.txt")

# ── Step 2: Register MCP server ────────────────────────────────────
section("2/4  Registering MCP server with Claude Code")
code, out, err = run(f'claude mcp add -s user context-iq "{PYTHON}" "{MCP_SCRIPT}"')
if code == 0:
    ok(f"MCP server registered: context-iq → {MCP_SCRIPT}")
else:
    if "already exists" in err.lower() or "already exists" in out.lower():
        ok("MCP server already registered")
    else:
        warn("Could not register MCP server automatically.")
        warn(f"Run manually:\n    claude mcp add -s user context-iq {PYTHON} \"{MCP_SCRIPT}\"")

# ── Step 3: settings.json snippets ─────────────────────────────────
section("3/4  Claude Code settings.json  (manual step)")
info("Open ~/.claude/settings.json and add these two blocks:\n")

statusline_path = STATUSLINE_SCRIPT.replace("\\", "\\\\") if IS_WIN else STATUSLINE_SCRIPT

print(f"""  "permissions": {{
    "allow": ["mcp__context-iq__*"]
  }},
  "statusLine": {{
    "type": "command",
    "command": "{PYTHON.replace(chr(92), chr(92)*2) if IS_WIN else PYTHON} {statusline_path}",
    "refreshInterval": 10
  }},""")

settings_path = os.path.expanduser("~/.claude/settings.json")
step(f"Edit: {settings_path}")

# ── Step 4: CLAUDE.md ──────────────────────────────────────────────
section("4/4  Global CLAUDE.md  (manual step)")
info("Create or open ~/.claude/CLAUDE.md and add:\n")

print("""  # ContextIQ — Auto Token Tracking

  After EVERY response you give, call the `context-iq__track_turn` MCP tool with:
  - `input_tokens`: your input token count for this turn
  - `output_tokens`: your output token count for this turn
  - `model`: your model name

  When the user asks "check context", "session health", or "intelligence score" — call
  `context-iq__get_intelligence_score` and show the result.

  When the user runs /clear or says "reset session" — call `context-iq__reset_session`.""")

claude_md_path = os.path.expanduser("~/.claude/CLAUDE.md")
step(f"Edit: {claude_md_path}")

# ── Done ───────────────────────────────────────────────────────────
section("Done")
print("""
  After completing steps 3 and 4:

  1. Restart Claude Code
  2. Status bar shows:  🟢 IQ:100 | 0tok | 0turns
  3. Ask anytime:       "check my context health"

  For standalone chat (needs Groq API key):
    cp .env.example .env   # add your GROQ_API_KEY
    python main.py
""")
