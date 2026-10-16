import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def assistant(used=0, cache_read=0, cache_write=0, out=100, model="claude-opus-5-5", sidechain=False, cwd="/proj"):
    return {
        "type": "assistant", "isSidechain": sidechain, "cwd": cwd, "sessionId": "s1",
        "message": {"model": model, "role": "assistant", "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": used, "cache_read_input_tokens": cache_read,
                              "cache_creation_input_tokens": cache_write, "output_tokens": out}},
    }


def user(text="hi"):
    return {"type": "user", "isSidechain": False, "message": {"role": "user", "content": text}}


def boundary():
    return {"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted",
            "compactMetadata": {"trigger": "manual", "preTokens": 150000}}


def payload(session="s1", used=1000, window=200_000, model="claude-opus-5-5", transcript=None, cwd="/proj"):
    usage = None if used is None else {"input_tokens": 3, "cache_read_input_tokens": used - 3,
                                       "cache_creation_input_tokens": 0, "output_tokens": 50}
    data = {"session_id": session, "cwd": cwd, "model": {"id": model, "display_name": "Opus"},
            "workspace": {"current_dir": cwd, "project_dir": cwd},
            "context_window": {"context_window_size": window, "current_usage": usage}}
    if transcript:
        data["transcript_path"] = transcript
    return data


class ConfigDirTestCase(unittest.TestCase):
    """Runs each test against a throwaway CLAUDE_CONFIG_DIR."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="contextiq-test-")
        self.config = os.path.join(self.tmp, "claude")
        os.makedirs(self.config)
        env = {"CLAUDE_CONFIG_DIR": self.config}
        for key in ("CONTEXT_IQ_QUALITY_WINDOW", "CONTEXT_IQ_WARN", "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
                    "CLAUDE_CODE_DISABLE_1M_CONTEXT"):
            env[key] = ""
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def transcript(self, entries, session="s1", project="-proj"):
        folder = os.path.join(self.config, "projects", project)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, session + ".jsonl")
        self.append(path, entries)
        return path

    @staticmethod
    def append(path, entries):
        with open(path, "a", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(entry) + "\n")

    def run_cli(self, *args, stdin=b""):
        env = dict(os.environ)
        env.pop("CONTEXT_IQ_DEBUG", None)
        return subprocess.run([sys.executable, os.path.join(ROOT, args[0])] + list(args[1:]),
                              input=stdin, capture_output=True, env=env, cwd=self.tmp, timeout=60)
