import json

import pytest

from contextiq import state, statusline


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_DIR", str(tmp_path / "context-iq"))
    monkeypatch.setattr(state, "LEGACY_STATE_FILE", str(tmp_path / "legacy.json"))
    yield tmp_path


def claude_code_payload(**overrides):
    payload = {
        "session_id": "abc123",
        "model": {"id": "claude-opus-4-8", "display_name": "Opus"},
        "cost": {"total_cost_usd": 0.12},
        "context_window": {
            "total_input_tokens": 15_500,
            "total_output_tokens": 1_200,
            "context_window_size": 200_000,
            "used_percentage": 8,
            "current_usage": {
                "input_tokens": 8_500,
                "output_tokens": 1_200,
                "cache_creation_input_tokens": 5_000,
                "cache_read_input_tokens": 2_000,
            },
        },
    }
    payload.update(overrides)
    return payload


def test_exact_usage_from_claude_code_payload():
    stats = statusline.stats_from_payload(claude_code_payload())
    assert stats.live_context_tokens == 16_700
    assert stats.context_window == 200_000
    assert stats.status == "fresh"


def test_build_output_renders_and_persists_state():
    out = statusline.build_output(json.dumps(claude_code_payload()))
    assert "IQ:" in out
    assert "$0.12" in out
    saved = state.read_state("abc123")
    assert saved["source"] == "claude-code"
    assert saved["live_context_tokens"] == 16_700


def test_used_percentage_fallback_when_no_current_usage():
    payload = claude_code_payload()
    payload["context_window"]["current_usage"] = {}
    stats = statusline.stats_from_payload(payload)
    assert stats.live_context_tokens == 16_000  # 8% of 200k


def test_no_context_data_returns_none():
    assert statusline.stats_from_payload({"model": {"id": "x"}}) is None


def test_empty_stdin_no_state_shows_ready():
    assert "ContextIQ ready" in statusline.build_output("")


def test_empty_stdin_falls_back_to_mcp_state():
    state.write_state({
        "status": "strained",
        "context_pressure_score": 25.0,
        "live_context_tokens": 150_000,
        "turns": 12,
    })
    out = statusline.build_output("")
    assert "IQ:25" in out


def test_garbage_stdin_does_not_crash():
    assert isinstance(statusline.build_output("{not json"), str)


def test_high_pressure_payload_goes_critical():
    payload = claude_code_payload()
    payload["context_window"]["current_usage"] = {
        "input_tokens": 190_000,
        "output_tokens": 4_000,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    stats = statusline.stats_from_payload(payload)
    assert stats.status == "critical"


def test_ascii_render_has_no_emoji():
    stats = statusline.stats_from_payload(claude_code_payload())
    line = statusline.render_line(stats, ascii_only=True)
    assert line.isascii()
