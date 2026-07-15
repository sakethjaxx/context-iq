from contextiq.meter import (
    DEFAULT_CONTEXT_WINDOW,
    SessionStats,
    resolve_context_window,
)


def make(model="claude-sonnet-4-6", live=0, **kw):
    s = SessionStats(model=model, **kw)
    if live:
        s.update_live_context(live)
    return s


def test_fresh_session_scores_100():
    s = make()
    assert s.context_pressure_score == 100.0
    assert s.status == "fresh"


def test_full_window_scores_zero():
    s = make(live=200_000)
    assert s.context_pressure_score == 0.0
    assert s.status == "critical"


def test_score_monotonically_decreases():
    scores = []
    for live in range(0, 200_001, 10_000):
        s = make(live=live)
        scores.append(s.context_pressure_score)
    assert scores == sorted(scores, reverse=True)


def test_status_bands_cover_all_levels():
    seen = set()
    for live in range(0, 200_001, 5_000):
        seen.add(make(live=live).status)
    assert seen == {"fresh", "warm", "strained", "critical"}


def test_compaction_detection_lowers_confidence():
    s = make()
    s.update_live_context(100_000)
    s.update_live_context(40_000)  # >30% drop
    assert s.confidence == "low"


def test_small_fluctuation_keeps_high_confidence():
    s = make()
    s.update_live_context(100_000)
    s.update_live_context(90_000)
    assert s.confidence == "high"


def test_unknown_model_defaults_window_and_medium_confidence():
    s = make(model="some-mystery-model")
    assert not s.context_window_known
    assert s.context_window == DEFAULT_CONTEXT_WINDOW
    assert s.confidence == "medium"


def test_dated_model_id_prefix_matches():
    assert resolve_context_window("claude-haiku-4-5-20251001") == 200_000
    assert resolve_context_window("claude-sonnet-5-20250929") == 200_000


def test_window_override_beats_lookup():
    s = SessionStats(model="some-mystery-model", context_window_override=500_000)
    assert s.context_window == 500_000
    assert s.context_window_known


def test_env_override(monkeypatch):
    monkeypatch.setenv("CONTEXTIQ_CONTEXT_WINDOW", "42000")
    assert resolve_context_window("anything") == 42_000


def test_ema_smooths_pressure():
    s = make()
    s.update_live_context(100_000)
    s.update_live_context(20_000)
    # EMA (60k) should sit between the raw values
    assert s.raw_pressure < s.context_pressure
