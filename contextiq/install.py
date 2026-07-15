"""
ContextIQ setup wizard.  Run after `pip install contextiq` (or `pip install .`):

    contextiq-setup

Configures the Claude Code status line (exact, automatic tracking) and
optionally registers the MCP server for Claude Desktop.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PYTHON = sys.executable
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
STATUSLINE_COMMAND = f'"{PYTHON}" -m contextiq.statusline' if " " in PYTHON else f"{PYTHON} -m contextiq.statusline"


def section(title):
    print(f"\n{'─' * 50}\n  {title}\n{'─' * 50}")


def ok(msg):    print(f"  [ok] {msg}")
def warn(msg):  print(f"  [!]  {msg}")
def info(msg):  print(f"  [i]  {msg}")


def ask_yes_no(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        return input(f"  {prompt} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def configure_statusline() -> None:
    section("1/2  Claude Code status line (exact tracking, no API key)")
    snippet = {
        "type": "command",
        "command": STATUSLINE_COMMAND,
    }
    settings = {}
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                settings = json.load(f)
        except ValueError:
            warn(f"Could not parse {SETTINGS_PATH} — add this manually:")
            print(f'\n  "statusLine": {json.dumps(snippet, indent=4)}\n')
            return

    existing = settings.get("statusLine")
    if existing == snippet:
        ok("Status line already configured")
        return
    if existing:
        info(f"A status line is already configured: {existing.get('command', existing)}")
        if not ask_yes_no("Replace it with ContextIQ?"):
            info("Keeping your existing status line. To use ContextIQ, set:")
            print(f'\n  "statusLine": {json.dumps(snippet, indent=4)}\n')
            return
    elif not ask_yes_no(f"Add ContextIQ status line to {SETTINGS_PATH}?"):
        info("Skipped. Add this to settings.json when ready:")
        print(f'\n  "statusLine": {json.dumps(snippet, indent=4)}\n')
        return

    if os.path.exists(SETTINGS_PATH):
        backup = f"{SETTINGS_PATH}.bak-{int(time.time())}"
        shutil.copy2(SETTINGS_PATH, backup)
        info(f"Backed up settings to {backup}")
    settings["statusLine"] = snippet
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    ok(f"Status line configured in {SETTINGS_PATH}")


def register_mcp() -> None:
    section("2/2  MCP server (optional — for Claude Desktop / hosts without a status line)")
    info("Claude Code users can skip this: the status line already tracks exactly.")
    if not ask_yes_no("Register the ContextIQ MCP server with Claude Code?"):
        info("Skipped. To register later:")
        print(f'\n    claude mcp add -s user context-iq "{PYTHON}" -m contextiq.mcp_server\n')
        return
    result = subprocess.run(
        ["claude", "mcp", "add", "-s", "user", "context-iq", PYTHON, "-m", "contextiq.mcp_server"],
        capture_output=True, text=True,
    )
    combined = (result.stdout + result.stderr).lower()
    if result.returncode == 0:
        ok("MCP server registered as context-iq")
    elif "already exists" in combined:
        ok("MCP server already registered")
    else:
        warn("Could not register automatically. Run manually:")
        print(f'\n    claude mcp add -s user context-iq "{PYTHON}" -m contextiq.mcp_server\n')


def main() -> None:
    print("\nContextIQ Setup\n")
    configure_statusline()
    register_mcp()
    section("Done")
    print("""
  1. Restart Claude Code
  2. The status line shows live context health as soon as the first response lands:
       IQ:96 | 15.2k/200k ctx (8%) | $0.01
  3. Optional live dashboard in another terminal:  contextiq-watch

  Standalone chat (needs an API key — Groq free tier works):
       cp .env.example .env   # add your key
       contextiq
""")


if __name__ == "__main__":
    main()
