import json
import os
import time
import unittest
from unittest import mock

from tests.helpers import ConfigDirTestCase, assistant, boundary, payload, user
import claude_code as cc


class StatuslinePayloadTest(ConfigDirTestCase):
    def test_current_usage_is_exact(self):
        snap = cc.from_statusline_payload(payload(used=150_000, window=1_000_000))
        self.assertTrue(snap.has_usage)
        self.assertEqual(snap.used_tokens, 150_000)
        self.assertEqual(snap.output_tokens, 50)
        self.assertEqual((snap.window, snap.window_source), (1_000_000, "claude-code"))

    def test_null_usage_before_first_reply_or_after_compact(self):
        self.assertFalse(cc.from_statusline_payload(payload(used=None)).has_usage)

    def test_used_percentage_only(self):
        data = {"session_id": "s1", "model": {"id": "claude-opus-5-5"},
                "context_window": {"context_window_size": 200_000, "used_percentage": 25}}
        snap = cc.from_statusline_payload(data)
        self.assertEqual(snap.used_tokens, 50_000)

    def test_missing_window_falls_back_to_model(self):
        data = {"session_id": "s1", "model": {"id": "claude-sonnet-4-6"}}
        snap = cc.from_statusline_payload(data)
        self.assertEqual((snap.window, snap.has_usage), (200_000, False))

    def test_unsafe_session_id_dropped(self):
        self.assertEqual(cc.from_statusline_payload(payload(session="../../etc")).session_id, "")


class DefaultWindowTest(unittest.TestCase):
    def window(self, model, **env):
        base = {"CLAUDE_CODE_MAX_CONTEXT_TOKENS": "", "CLAUDE_CODE_DISABLE_1M_CONTEXT": ""}
        base.update(env)
        with mock.patch.dict(os.environ, base):
            return cc.default_window(model)[0]

    def test_models(self):
        self.assertEqual(self.window("claude-opus-5-5"), 1_000_000)
        self.assertEqual(self.window("claude-fable-5-1"), 1_000_000)
        self.assertEqual(self.window("claude-sonnet-5"), 1_000_000)
        self.assertEqual(self.window("claude-opus-4-7"), 1_000_000)
        self.assertEqual(self.window("us.anthropic.claude-opus-4-8-v1:0"), 1_000_000)
        self.assertEqual(self.window("claude-sonnet-4-6"), 200_000)
        self.assertEqual(self.window("claude-sonnet-4-6[1m]"), 1_000_000)
        self.assertEqual(self.window("claude-haiku-4-5"), 200_000)
        self.assertEqual(self.window("my-gateway-alias"), 200_000)

    def test_env(self):
        self.assertEqual(self.window("claude-opus-5-5", CLAUDE_CODE_DISABLE_1M_CONTEXT="1"), 200_000)
        self.assertEqual(self.window("anything", CLAUDE_CODE_MAX_CONTEXT_TOKENS="400000"), 400_000)


class TranscriptTest(ConfigDirTestCase):
    def test_latest_main_chain_usage(self):
        path = self.transcript([user(), assistant(used=10, cache_read=1000, cache_write=90), user(),
                                assistant(used=5, cache_read=5000, cache_write=0, out=7)])
        found = cc.read_transcript_usage(path)
        self.assertEqual((found["used"], found["output"], found["compacted"]), (5005, 7, False))
        self.assertEqual(found["model"], "claude-opus-5-5")

    def test_skips_sidechain_synthetic_and_garbage(self):
        path = self.transcript([assistant(cache_read=4000), assistant(cache_read=99_000, sidechain=True),
                                assistant(used=0, out=0, model="<synthetic>")])
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('{"type": "assistant", "usage": broken\n')
        self.assertEqual(cc.read_transcript_usage(path)["used"], 4000)

    def test_compact_boundary_after_usage(self):
        path = self.transcript([assistant(cache_read=150_000), boundary(), user("summary")])
        found = cc.read_transcript_usage(path)
        self.assertTrue(found["compacted"])

    def test_usage_after_boundary(self):
        path = self.transcript([assistant(cache_read=150_000), boundary(), assistant(cache_read=12_000)])
        self.assertEqual(cc.read_transcript_usage(path)["used"], 12_000)

    def test_text_mentioning_boundary_is_not_a_boundary(self):
        path = self.transcript([assistant(cache_read=8000), user('look for "compact_boundary" in the log')])
        self.assertEqual(cc.read_transcript_usage(path)["used"], 8000)

    def test_lines_larger_than_read_chunk(self):
        big = assistant(cache_read=77_000)
        big["message"]["content"][0]["text"] = "x" * (3 * cc._TAIL_CHUNK)
        filler = [user("y" * 1000) for _ in range(300)]
        path = self.transcript(filler + [assistant(cache_read=1)] + filler + [big, user("z" * 70_000)])
        self.assertEqual(cc.read_transcript_usage(path)["used"], 77_000)

    def test_usage_on_first_line_of_file(self):
        path = self.transcript([assistant(cache_read=321)])
        self.assertEqual(cc.read_transcript_usage(path)["used"], 321)

    def test_missing_or_empty(self):
        self.assertIsNone(cc.read_transcript_usage(os.path.join(self.tmp, "nope.jsonl")))
        self.assertIsNone(cc.read_transcript_usage(None))
        self.assertIsNone(cc.read_transcript_usage(self.transcript([user()])))

    def test_find_transcript(self):
        path = self.transcript([user()], session="abc-123", project="-home-me-proj")
        self.assertEqual(cc.find_transcript("abc-123"), path)
        self.assertIsNone(cc.find_transcript("../abc-123"))
        self.assertEqual(cc.latest_transcript_for_cwd("/home/me/proj"), path)


class ResolveSnapshotTest(ConfigDirTestCase):
    def test_reuses_status_line_window_for_same_model(self):
        cc.save_state(cc.from_statusline_payload(payload(used=1000, window=200_000, model="claude-opus-5-5")))
        path = self.transcript([assistant(cache_read=150_000)])
        snap = cc.resolve_snapshot("s1", path)
        self.assertEqual((snap.window, snap.window_source, snap.used_tokens), (200_000, "claude-code", 150_000))

    def test_model_switch_ignores_stale_window(self):
        cc.save_state(cc.from_statusline_payload(payload(window=200_000, model="claude-haiku-4-5")))
        path = self.transcript([assistant(cache_read=10_000, model="claude-opus-5-5")])
        self.assertEqual(cc.resolve_snapshot("s1", path).window, 1_000_000)

    def test_infers_1m_when_usage_exceeds_window(self):
        path = self.transcript([assistant(cache_read=350_000, model="claude-sonnet-4-6")])
        snap = cc.resolve_snapshot("s1", path)
        self.assertEqual((snap.window, snap.window_source), (1_000_000, "inferred"))

    def test_falls_back_to_state_without_transcript(self):
        cc.save_state(cc.from_statusline_payload(payload(used=42_000)))
        self.assertEqual(cc.resolve_snapshot("s1").used_tokens, 42_000)
        self.assertIsNone(cc.resolve_snapshot("unknown"))


class StateStoreTest(ConfigDirTestCase):
    def test_roundtrip_and_merge(self):
        snap = cc.from_statusline_payload(payload(used=5000))
        self.assertTrue(cc.save_state(snap, last_warned="strained"))
        self.assertTrue(cc.save_state(snap))
        state = cc.load_state("s1")
        self.assertEqual((state["used_tokens"], state["last_warned"], state["status"]), (5000, "strained", "fresh"))
        self.assertEqual(cc.Snapshot.from_dict(state).used_tokens, 5000)

    def test_latest_state_filters(self):
        a = cc.from_statusline_payload(payload(session="a", cwd="/one"))
        b = cc.from_statusline_payload(payload(session="b", cwd="/two"))
        a.updated_at, b.updated_at = time.time() - 100, time.time()
        cc.save_state(a)
        cc.save_state(b)
        self.assertEqual(cc.latest_state()["session_id"], "b")
        self.assertEqual(cc.latest_state(cwd="/one")["session_id"], "a")
        self.assertIsNone(cc.latest_state(cwd="/one", max_age=10))

    def test_prune(self):
        cc.save_state(cc.from_statusline_payload(payload(session="old")))
        old = os.path.join(cc.state_dir(), "old.json")
        os.utime(old, (time.time() - cc.STATE_MAX_AGE - 10,) * 2)
        cc.prune_states()
        self.assertFalse(os.path.exists(old))

    def test_corrupt_state_ignored(self):
        os.makedirs(cc.state_dir())
        with open(os.path.join(cc.state_dir(), "s1.json"), "w") as fh:
            fh.write("{nope")
        self.assertIsNone(cc.load_state("s1"))
        self.assertIsNone(cc.latest_state())


class RenderTest(ConfigDirTestCase):
    def test_fmt_tokens(self):
        self.assertEqual([cc.fmt_tokens(n) for n in (950, 1000, 8500, 15_500, 200_000, 1_000_000, 1_250_000)],
                         ["950", "1k", "8.5k", "16k", "200k", "1M", "1.2M"])

    def test_statusline_text(self):
        with mock.patch.dict(os.environ, {"CONTEXT_IQ_QUALITY_WINDOW": ""}):
            fresh = cc.render_statusline(cc.from_statusline_payload(payload(used=16_000, window=1_000_000)))
            self.assertIn("IQ:100 fresh | 16k/1M ctx", fresh)
            critical = cc.render_statusline(cc.from_statusline_payload(payload(used=190_000, window=200_000)))
            self.assertTrue(critical.endswith("/compact now"))
        self.assertIn("ready", cc.render_statusline(None))
        self.assertIn("compacted", cc.render_statusline(cc.Snapshot(compacted=True)))

    def test_report(self):
        report = cc.render_report(cc.from_statusline_payload(payload(used=100_000, window=1_000_000)))
        self.assertIn("100,000 tokens", report)
        self.assertIn("Quality horizon", report)
        self.assertIn("no usage", cc.render_report(None))


if __name__ == "__main__":
    unittest.main()
