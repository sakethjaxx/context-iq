"""ContextIQ installer for Claude Code. Standard library only, no API key.

    python3 install.py               status line + early-warning hook + health skill
    python3 install.py --dry-run     show what would change, write nothing
    python3 install.py --uninstall   remove everything ContextIQ added

Options:
    --statusline-only   only set up the status line (used by the plugin)
    --copy              run from a copy in ~/.claude/context-iq/runtime instead of this folder
    --force             replace a status line that isn't ContextIQ's
    --with-mcp          also register the optional MCP server (installs the `mcp` package)
    --settings PATH     settings file to edit (default: ~/.claude/settings.json)

Your settings file is backed up before any change, and unrelated settings are left alone.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import claude_code as cc  # noqa: E402

RUNTIME_FILES = ("contextiq.py", "statusline.py", "claude_code.py", "meter.py")
SKILL_TEMPLATE = os.path.join(HERE, "skills", "context-health", "SKILL.md")
PLUGIN_COMMAND = 'python3 "${CLAUDE_PLUGIN_ROOT}/contextiq.py"'
PYTHON_HINT = " (use `python` instead of `python3` if `python3` is not found)"
MCP_PERMISSIONS = ("mcp__context-iq", "mcp__context-iq__*")
_SAFE_ARG = re.compile(r"^[\w@%+=:,./~-]+$")


# ── helpers ──────────────────────────────────────────────────────────────

def say(tag: str, msg: str) -> None:
    print(f"  [{tag}] {msg}")


def stable_python() -> str:
    """The interpreter for stdlib-only scripts; avoids pinning a throwaway virtualenv."""
    base = getattr(sys, "_base_executable", None)
    if sys.prefix != sys.base_prefix and base and os.path.isfile(base):
        return base
    return sys.executable


def shell_path(path: str) -> str:
    # Git Bash on Windows eats backslashes; Claude Code's docs recommend forward slashes.
    return path.replace("\\", "/") if os.name == "nt" else path


def quote(arg: str) -> str:
    if _SAFE_ARG.match(arg):
        return arg
    return f'"{arg}"' if os.name == "nt" else shlex.quote(arg)


def command(*parts: str) -> str:
    return " ".join(quote(shell_path(p)) for p in parts)


def norm(cmd: str) -> str:
    return (cmd or "").replace("\\", "/").lower()


def is_our_statusline(cmd: str, runtime_dirs) -> bool:
    c = norm(cmd)
    if "statusline.py" not in c and "contextiq.py" not in c:
        return False
    if "context-iq" in c or "contextiq" in c:
        return True
    return any(norm(os.path.join(d, "statusline.py")) in c for d in runtime_dirs)


def is_our_hook(cmd: str) -> bool:
    c = norm(cmd).strip().rstrip('"\'')
    return "contextiq.py" in c and c.endswith(" hook")


def plugin_enabled(settings: dict) -> bool:
    plugins = settings.get("enabledPlugins") or {}
    return isinstance(plugins, dict) and any(
        str(name).split("@")[0] == "context-iq" and on for name, on in plugins.items())


def strip_our_hooks(groups):
    """Remove ContextIQ hook entries; drop matcher groups that only held ours."""
    kept, removed = [], 0
    for group in groups if isinstance(groups, list) else []:
        inner = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(inner, list):
            kept.append(group)
            continue
        mine = [h for h in inner if isinstance(h, dict) and is_our_hook(h.get("command", ""))]
        removed += len(mine)
        if mine and len(mine) == len(inner):
            continue
        if mine:
            group = dict(group, hooks=[h for h in inner if h not in mine])
        kept.append(group)
    return kept, removed


def load_settings(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("top level is not a JSON object")
    return data


def save_settings(path: str, old: dict, new: dict, dry_run: bool) -> None:
    if new == old:
        say("ok", f"{path} already up to date")
        return
    if dry_run:
        say("dry-run", f"would write {path}:")
        print(json.dumps({k: new[k] for k in new if new.get(k) != old.get(k)}, indent=2, ensure_ascii=False))
        return
    if os.path.exists(path):
        backup = f"{path}.bak-contextiq-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(path, backup)
        say("ok", f"backed up settings to {backup}")
    if not cc.write_json_atomic(path, new, ensure_ascii=False):
        raise OSError(f"could not write {path}")
    say("ok", f"updated {path}")


def in_plugin_cache(path: str) -> bool:
    return "/plugins/cache/" in norm(path) + "/"


def copy_runtime(dry_run: bool) -> str:
    target = os.path.join(cc.data_dir(), "runtime")
    if dry_run:
        say("dry-run", f"would copy {', '.join(RUNTIME_FILES)} to {target}")
        return target
    os.makedirs(target, exist_ok=True)
    for name in RUNTIME_FILES:
        shutil.copy2(os.path.join(HERE, name), os.path.join(target, name))
    say("ok", f"copied runtime to {target}")
    return target


def skill_path() -> str:
    return os.path.join(cc.config_dir(), "skills", "context-health", "SKILL.md")


def render_skill(py: str, runtime: str) -> str:
    with open(SKILL_TEMPLATE, encoding="utf-8") as fh:
        text = fh.read()
    return (text.replace(PLUGIN_COMMAND, command(py, os.path.join(runtime, "contextiq.py")))
                .replace(PYTHON_HINT, ""))


def legacy_notices() -> None:
    claude_md = os.path.join(cc.config_dir(), "CLAUDE.md")
    try:
        with open(claude_md, encoding="utf-8") as fh:
            if "track_turn" in fh.read():
                say("note", f"{claude_md} still tells Claude to call track_turn after every reply. "
                            "ContextIQ reads exact usage from Claude Code now, so delete that "
                            "'ContextIQ' block to stop spending tokens on it each turn.")
    except OSError:
        pass


# ── install / uninstall ──────────────────────────────────────────────────

def plan_install(settings: dict, runtime: str, args) -> dict:
    new = copy.deepcopy(settings)
    py = stable_python()

    current = new.get("statusLine")
    current_cmd = current.get("command", "") if isinstance(current, dict) else ""
    if current and not is_our_statusline(current_cmd, (HERE, runtime)) and not args.force:
        say("skip", f"kept your existing status line: {current_cmd or current!r}")
        say("skip", "rerun with --force to replace it (warnings and health checks work either way)")
    else:
        line = {"type": "command", "command": command(py, os.path.join(runtime, "statusline.py"))}
        if isinstance(current, dict) and "padding" in current:
            line["padding"] = current["padding"]
        new["statusLine"] = line
        say("ok", "status line: " + line["command"])

    if args.with_mcp:
        allow = new.setdefault("permissions", {}).setdefault("allow", [])
        if MCP_PERMISSIONS[0] not in allow:
            allow.append(MCP_PERMISSIONS[0])

    if args.statusline_only:
        return new
    if plugin_enabled(new):
        say("skip", "the context-iq plugin is enabled and already provides the warning hook")
        return new

    hooks = new.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError('"hooks" in settings is not an object')
    stop, _ = strip_our_hooks(hooks.get("Stop", []))
    hook_cmd = command(py, os.path.join(runtime, "contextiq.py")) + " hook"
    stop.append({"hooks": [{"type": "command", "command": hook_cmd, "timeout": 10}]})
    hooks["Stop"] = stop
    say("ok", "warning hook (Stop): " + hook_cmd)
    return new


def install_skill(py: str, runtime: str, settings: dict, dry_run: bool) -> None:
    if plugin_enabled(settings):
        return
    path = skill_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            if "contextiq.py" not in fh.read():
                say("skip", f"{path} exists and isn't ContextIQ's; left alone")
                return
    if dry_run:
        say("dry-run", f"would write health skill to {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_skill(py, runtime))
    say("ok", f'health skill: ask "check my context health" in any session ({path})')


def install_mcp(dry_run: bool) -> None:
    py = sys.executable  # the MCP server needs the interpreter that has `mcp`
    server = os.path.join(HERE, "mcp_server.py")
    if dry_run:
        say("dry-run", f"would ensure `mcp` is installed for {py} and run: claude mcp add --scope user context-iq")
        return
    try:
        import mcp  # noqa: F401
    except ImportError:
        say("..", "installing the `mcp` package")
        result = subprocess.run([py, "-m", "pip", "install", "-q", "mcp>=1.2"], capture_output=True, text=True)
        if result.returncode != 0:
            say("warn", "pip install failed; install `mcp` in a virtualenv and rerun from there:")
            print("      " + (result.stderr.strip().splitlines() or ["(no output)"])[-1])
            return
    claude = shutil.which("claude")
    args = ["mcp", "add", "--scope", "user", "context-iq", "--", py, server]
    if not claude:
        say("warn", "`claude` CLI not found; register the server yourself:")
        print("      claude " + " ".join(quote(a) for a in args))
        return
    result = subprocess.run([claude] + args, capture_output=True, text=True)
    output = (result.stdout + result.stderr).lower()
    if result.returncode == 0:
        say("ok", "MCP server registered as context-iq")
    elif "already exists" in output:
        say("ok", "MCP server already registered")
    else:
        say("warn", "could not register the MCP server: " + (result.stderr or result.stdout).strip())


def uninstall(path: str, settings: dict, args) -> int:
    new = copy.deepcopy(settings)
    runtime = os.path.join(cc.data_dir(), "runtime")
    line = new.get("statusLine")
    if isinstance(line, dict) and (is_our_statusline(line.get("command", ""), (HERE, runtime)) or args.force):
        del new["statusLine"]
        say("ok", "removed status line")
    hooks = new.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks):
            kept, removed = strip_our_hooks(hooks[event])
            if removed:
                say("ok", f"removed {removed} {event} hook(s)")
                if kept:
                    hooks[event] = kept
                else:
                    del hooks[event]
        if not hooks:
            del new["hooks"]
    allow = (new.get("permissions") or {}).get("allow")
    if isinstance(allow, list) and any(p in allow for p in MCP_PERMISSIONS):
        new["permissions"]["allow"] = [p for p in allow if p not in MCP_PERMISSIONS]
    save_settings(path, settings, new, args.dry_run)

    skill = skill_path()
    if os.path.exists(skill):
        with open(skill, encoding="utf-8") as fh:
            ours = "contextiq.py" in fh.read()
        if ours and not args.dry_run:
            shutil.rmtree(os.path.dirname(skill), ignore_errors=True)
            say("ok", "removed health skill")
    claude = shutil.which("claude")
    if claude and not args.dry_run:
        result = subprocess.run([claude, "mcp", "remove", "--scope", "user", "context-iq"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            say("ok", "removed MCP server registration")
    for leftover in (cc.data_dir(), os.path.join(cc.config_dir(), "context-iq-state.json")):
        if os.path.exists(leftover) and not args.dry_run:
            shutil.rmtree(leftover, ignore_errors=True) if os.path.isdir(leftover) else os.remove(leftover)
            say("ok", f"removed {leftover}")
    legacy_notices()
    print("\n  ContextIQ removed. If you installed the plugin, also run: /plugin uninstall context-iq\n")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Install ContextIQ into Claude Code.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--statusline-only", action="store_true")
    parser.add_argument("--copy", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--with-mcp", action="store_true")
    parser.add_argument("--settings")
    args = parser.parse_args(argv)

    path = args.settings or os.path.join(cc.config_dir(), "settings.json")
    print(f"\nContextIQ {'uninstall' if args.uninstall else 'setup'}\n")
    try:
        settings = load_settings(path)
    except (OSError, ValueError) as exc:
        say("error", f"can't read {path}: {exc}")
        say("error", "fix the file (or pass --settings) and rerun; nothing was changed")
        return 1

    if args.uninstall:
        return uninstall(path, settings, args)

    runtime = HERE
    if args.copy or in_plugin_cache(HERE):
        runtime = copy_runtime(args.dry_run)
    try:
        new = plan_install(settings, runtime, args)
        save_settings(path, settings, new, args.dry_run)
    except (OSError, ValueError) as exc:
        say("error", str(exc))
        return 1
    if not args.statusline_only:
        install_skill(stable_python(), runtime, new, args.dry_run)
    if args.with_mcp:
        install_mcp(args.dry_run)
    legacy_notices()

    if not args.dry_run:
        print(f"""
  Done. Start a new Claude Code session (or restart it) to load everything.
  After Claude's first reply the status line reads like:  IQ:100 fresh | 16k/1M ctx
  Check anytime:  {command(stable_python(), os.path.join(runtime, 'contextiq.py'))} health
  Remove:         {command(sys.executable, os.path.join(HERE, 'install.py'))} --uninstall
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
