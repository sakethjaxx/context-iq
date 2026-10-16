---
name: setup-statusline
description: Add the ContextIQ score to the Claude Code status line. One-time setup after installing the plugin.
disable-model-invocation: true
---

Run this command with the Bash tool (use `python` instead of `python3` if `python3` is not found):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/install.py" --statusline-only --copy
```

Show the user the output. If it says their existing status line was kept, ask whether to replace it; if they agree, run the same command again with `--force` added. The ContextIQ status line appears after the next reply.
