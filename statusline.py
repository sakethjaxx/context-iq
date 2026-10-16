"""ContextIQ status line for Claude Code.

Kept at this path so settings written by earlier versions keep working:
    {"statusLine": {"type": "command", "command": "python3 /path/to/context-iq/statusline.py"}}

Claude Code pipes the session's exact context usage to this script on stdin.
"""
import sys

from contextiq import main

if __name__ == "__main__":
    sys.exit(main(["statusline"]))
