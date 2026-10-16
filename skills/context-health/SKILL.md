---
name: context-health
description: Check this Claude Code session's context health with ContextIQ (score 0-100, tokens in context, and whether to /compact or /clear). Use when the user asks to check context, session health, how fresh you are, or for the intelligence score.
---

Run this command with the Bash tool (use `python` instead of `python3` if `python3` is not found):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/contextiq.py" health --session "${CLAUDE_SESSION_ID}"
```

Then tell the user, in two or three short lines, the score and status, how many tokens are in context, and the recommendation. If the status is strained or critical, suggest `/compact` (keeps a summary and continues) or `/clear` (starts fresh).
