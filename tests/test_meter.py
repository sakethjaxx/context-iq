import os
import unittest
from unittest import mock

from tests import helpers  # noqa: F401  (puts the repo root on sys.path)
import meter
from meter import SessionStats, effective_window, lookup_context_window, quality_window, score_for_pressure, status_for_score


class ScoreCurveTest(unittest.TestCase):
    def test_endpoints_and_monotonic(self):
        self.assertEqual(score_for_pressure(0.0), 100.0)
        self.assertEqual(score_for_pressure(1.0), 0.0)
        scores = [score_for_pressure(p / 100) for p in range(0, 101)]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_clamps_out_of_range(self):
        self.assertEqual(score_for_pressure(-1), 100.0)
        self.assertEqual(score_for_pressure(5), 0.0)

    def test_status_bands(self):
        self.assertEqual(status_for_score(score_for_pressure(0.50)), "fresh")
        self.assertEqual(status_for_score(score_for_pressure(0.75)), "warm")
        self.assertEqual(status_for_score(score_for_pressure(0.84)), "strained")
        self.assertEqual(status_for_score(score_for_pressure(0.95)), "critical")


class QualityWindowTest(unittest.TestCase):
    def test_default_caps_large_windows_only(self):
        with mock.patch.dict(os.environ, {"CONTEXT_IQ_QUALITY_WINDOW": ""}):
            self.assertEqual(quality_window(), meter.DEFAULT_QUALITY_WINDOW)
            self.assertEqual(effective_window(1_000_000), meter.DEFAULT_QUALITY_WINDOW)
            self.assertEqual(effective_window(200_000), 200_000)

    def test_env_override_and_disable(self):
        with mock.patch.dict(os.environ, {"CONTEXT_IQ_QUALITY_WINDOW": "200_000"}):
            self.assertEqual(effective_window(1_000_000), 200_000)
        with mock.patch.dict(os.environ, {"CONTEXT_IQ_QUALITY_WINDOW": "0"}):
            self.assertEqual(effective_window(1_000_000), 1_000_000)
        with mock.patch.dict(os.environ, {"CONTEXT_IQ_QUALITY_WINDOW": "lots"}):
            self.assertEqual(quality_window(), meter.DEFAULT_QUALITY_WINDOW)


class ModelWindowTest(unittest.TestCase):
    def test_lookup_variants(self):
        self.assertEqual(lookup_context_window("claude-opus-5-5"), 1_000_000)
        self.assertEqual(lookup_context_window("claude-haiku-4-5-20251001"), 200_000)
        self.assertEqual(lookup_context_window("us.anthropic.claude-haiku-4-5-v1:0"), 200_000)
        self.assertEqual(lookup_context_window("claude-haiku-4-5[1m]"), 1_000_000)
        self.assertIsNone(lookup_context_window("mystery-model"))


class SessionStatsTest(unittest.TestCase):
    def test_large_window_scored_against_horizon(self):
        with mock.patch.dict(os.environ, {"CONTEXT_IQ_QUALITY_WINDOW": ""}):
            s = SessionStats(model="claude-opus-5-5")
            s.update_live_context(370_000)
            self.assertEqual(s.context_window, 1_000_000)
            self.assertEqual(s.effective_window, meter.DEFAULT_QUALITY_WINDOW)
            self.assertIn(s.status, ("strained", "critical"))

    def test_unknown_model_defaults(self):
        s = SessionStats(model="mystery")
        self.assertFalse(s.context_window_known)
        self.assertEqual(s.confidence, "medium")
        self.assertEqual(s.context_window, meter.DEFAULT_CONTEXT_WINDOW)

    def test_compaction_drop_lowers_confidence(self):
        s = SessionStats(model="claude-haiku-4-5")
        s.update_live_context(150_000)
        s.update_live_context(20_000)
        self.assertEqual(s.confidence, "low")


if __name__ == "__main__":
    unittest.main()
