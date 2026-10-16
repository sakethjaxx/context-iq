import json
import os
import unittest
from unittest import mock

from tests.helpers import ConfigDirTestCase, assistant, boundary, payload, user
import claude_code as cc
import contextiq


class StatuslineCommandTest(ConfigDirTestCase):
    def test_prints_score_and_saves_state(self):
        result = self.run_cli("statusline.py", stdin=json.dumps(payload(used=16_000, window=1_000_000)).encode())
        self.assertEqual(result.returncode, 0)
        self.assertIn("IQ:100 fresh | 16k/1M ctx", result.stdout.decode("utf-8"))
        self.assertEqual(cc.load_state("s1")["window_source"], "claude-code")

    def test_bad_input_never_fails(self):
        for stdin in (b"", b"not json", b"[1, 2]", b"\xff\xfe garbage"):
            result = self.run_cli("contextiq.py", "statusline", stdin=stdin)
            self.assertEqual(result.returncode, 0)
            self.assertIn("ContextIQ", result.stdout.decode("utf-8"))
            self.assertEqual(result.stderr, b"")

    def test_falls_back_to_transcript_when_usage_is_null(self):
        path = self.transcript([assistant(cache_read=60_000)])
        line = contextiq.statusline(payload(used=None, window=200_000, transcript=path))
        self.assertIn("60k/200k", line)

    def test_skips_redundant_state_writes(self):
        contextiq.statusline(payload(used=5000))
        first = cc.load_state("s1")["updated_at"]
        contextiq.statusline(payload(used=5000))
        self.assertEqual(cc.load_state("s1")["updated_at"], first)
        contextiq.statusline(payload(used=6000))
        self.assertEqual(cc.load_state("s1")["used_tokens"], 6000)


class HookTest(ConfigDirTestCase):
    def setUp(self):
        super().setUp()
        # 200k window from the status line keeps the numbers readable.
        cc.save_state(cc.from_statusline_payload(payload(window=200_000)))
        self.path = self.transcript([user()])

    def reply(self, tokens):
        self.append(self.path, [assistant(cache_read=tokens), user()])
        return contextiq.hook({"session_id": "s1", "transcript_path": self.path, "cwd": "/proj"})

    def test_warns_once_per_level_and_rearms_after_compact(self):
        self.assertIsNone(self.reply(50_000))                 # fresh
        self.assertIsNone(self.reply(145_000))                # warm
        self.assertIn("strained", self.reply(165_000))
        self.assertIsNone(self.reply(166_000))                # still strained: quiet
        self.assertIn("critical", self.reply(185_000))
        self.assertIsNone(self.reply(186_000))
        self.append(self.path, [boundary()])
        self.assertIsNone(contextiq.hook({"session_id": "s1", "transcript_path": self.path}))
        self.assertIsNone(self.reply(20_000))
        self.assertIn("strained", self.reply(165_000))        # re-armed

    def test_warning_level_setting(self):
        with mock.patch.dict(os.environ, {"CONTEXT_IQ_WARN": "critical"}):
            self.assertIsNone(self.reply(165_000))
            self.assertIn("critical", self.reply(185_000))
        with mock.patch.dict(os.environ, {"CONTEXT_IQ_WARN": "off"}):
            self.append(self.path, [boundary()])
            contextiq.hook({"session_id": "s1", "transcript_path": self.path})
            self.assertIsNone(self.reply(190_000))

    def test_subprocess_output_is_hook_json(self):
        self.append(self.path, [assistant(cache_read=190_000)])
        stdin = json.dumps({"session_id": "s1", "transcript_path": self.path, "hook_event_name": "Stop"}).encode()
        result = self.run_cli("contextiq.py", "hook", stdin=stdin)
        self.assertEqual(result.returncode, 0)
        self.assertIn("critical", json.loads(result.stdout)["systemMessage"])

    def test_subprocess_bad_input_is_silent(self):
        for stdin in (b"", b"{", json.dumps({"session_id": "nope"}).encode()):
            result = self.run_cli("contextiq.py", "hook", stdin=stdin)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))


class HealthCommandTest(ConfigDirTestCase):
    def test_json_for_session(self):
        self.transcript([assistant(cache_read=90_000)], session="abc")
        result = self.run_cli("contextiq.py", "health", "--session", "abc", "--json")
        data = json.loads(result.stdout)
        self.assertEqual((data["used_tokens"], data["status"]), (90_000, "fresh"))

    def test_latest_session_for_cwd(self):
        self.transcript([assistant(cache_read=12_345)], session="here", project=cc.project_key("/work/app"))
        snap = contextiq.health_snapshot(cwd="/work/app")
        self.assertEqual(snap.used_tokens, 12_345)

    def test_unsubstituted_placeholder_falls_back(self):
        self.assertIsNone(contextiq.health_snapshot("${CLAUDE_SESSION_ID}", cwd="/nothing/here"))
        result = self.run_cli("contextiq.py", "health", "--session", "${CLAUDE_SESSION_ID}")
        self.assertIn("no usage recorded", result.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
