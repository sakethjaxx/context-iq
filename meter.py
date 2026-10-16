"""Intelligence score: how much context pressure a session is under.

Standard library only — the Claude Code status line and hook import this on
every refresh.
"""
import math
import os
import re
from dataclasses import dataclass, field
from typing import Literal

# API context windows, used by the standalone chat. Claude Code reports its own
# window to the status line, so the Claude Code integration rarely needs these.
MODEL_CONTEXT_WINDOWS = {
    # Claude
    "claude-fable-5-1": 1_000_000,
    "claude-fable-5": 1_000_000,
    "claude-opus-5-5": 1_000_000,
    "claude-opus-5": 1_000_000,
    "claude-opus-4-8": 1_000_000,
    "claude-opus-4-7": 1_000_000,
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-5-5": 1_000_000,
    "claude-sonnet-5": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-haiku-5-5": 1_000_000,
    "claude-haiku-4-5": 200_000,
    # Groq / Llama
    "llama-3.3-70b-versatile": 128_000,
    "llama-3.1-70b-versatile": 128_000,
    "llama-3.1-8b-instant": 131_072,
    "llama3-70b-8192": 8_192,
    "llama3-8b-8192": 8_192,
    # Groq / other
    "mixtral-8x7b-32768": 32_768,
    "gemma2-9b-it": 8_192,
    "gemma-7b-it": 8_192,
}
DEFAULT_CONTEXT_WINDOW = 128_000
RESPONSE_RESERVE = 4_096
COMPACTION_DROP_THRESHOLD = 0.30
EMA_ALPHA = 0.5  # weight of newest turn in rolling average

# Quality horizon: answer quality degrades with the absolute number of tokens in
# context, not only with the fraction of the window used. Without a horizon a
# 1M-token window would read "fresh" at 600k tokens. Pressure is measured against
# min(context window, horizon), so 200k-window models are unaffected. This is a
# heuristic: set CONTEXT_IQ_QUALITY_WINDOW=200000 for earlier warnings, or 0 to
# score against the full window.
DEFAULT_QUALITY_WINDOW = 400_000

# Logistic scoring curve: plateau 0-40%, noticeable 40-70%, sharp 70-90%, cliff 90%+
_SCORE_K = 14       # steepness
_SCORE_C = 0.78     # inflection point (78% pressure)
_SCORE_LO = 1 / (1 + math.exp(_SCORE_K * (1.0 - _SCORE_C)))
_SCORE_HI = 1 / (1 + math.exp(_SCORE_K * (0.0 - _SCORE_C)))

Status = Literal["fresh", "warm", "strained", "critical"]

STATUS_RANK = {"fresh": 0, "warm": 1, "strained": 2, "critical": 3}

STATUS_COLORS = {
    "fresh": "green",
    "warm": "yellow",
    "strained": "orange3",
    "critical": "red",
}

RECOMMENDATIONS = {
    "fresh":    "Session healthy. No action needed.",
    "warm":     "Session warming up. Run /compact at the next natural break.",
    "strained": "High context pressure; answer quality may be slipping. Run /compact soon, or /clear when you switch tasks.",
    "critical": "Critical context pressure. Run /compact now, or /clear to start fresh.",
}


def quality_window() -> int:
    """Token horizon past which quality is treated as degraded (0 = no horizon)."""
    raw = os.environ.get("CONTEXT_IQ_QUALITY_WINDOW", "").strip().replace("_", "")
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return DEFAULT_QUALITY_WINDOW


def effective_window(context_window: int) -> int:
    """The window pressure is scored against: the smaller of window and horizon."""
    horizon = quality_window()
    if horizon and context_window > horizon:
        return horizon
    return context_window


def score_for_pressure(pressure: float) -> float:
    """0-100. Logistic: plateau until ~40% pressure, cliff at 90%+."""
    pressure = min(1.0, max(0.0, pressure))
    raw = 1 / (1 + math.exp(_SCORE_K * (pressure - _SCORE_C)))
    return max(0.0, round(100 * (raw - _SCORE_LO) / (_SCORE_HI - _SCORE_LO), 1))


def status_for_score(score: float) -> Status:
    if score >= 70:
        return "fresh"
    elif score >= 40:
        return "warm"
    elif score >= 15:
        return "strained"
    return "critical"


def normalize_model_id(model: str) -> str:
    """'us.anthropic.claude-opus-4-7-v1:0' / 'claude-haiku-4-5-20251001' -> table key."""
    m = (model or "").strip().lower()
    m = re.sub(r"\[[^\]]*\]$", "", m)            # [1m] suffix
    idx = m.find("claude-")
    if idx > 0:                                  # Bedrock / Vertex prefixes
        m = m[idx:]
    m = re.sub(r"[-@]\d{8}$", "", m)             # dated snapshot
    m = re.sub(r"-v\d+(:\d+)?$", "", m)          # Bedrock version suffix
    return m


def lookup_context_window(model: str):
    """Known API context window for a model id, or None."""
    if "[1m]" in (model or "").lower():
        return 1_000_000
    return MODEL_CONTEXT_WINDOWS.get(model) or MODEL_CONTEXT_WINDOWS.get(normalize_model_id(model))


@dataclass
class SessionStats:
    model: str
    turns: int = 0
    # Cumulative — use for cost/spend tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    # Live — effective_input (incl. cache) + output; use for health/pressure
    live_context_tokens: int = 0
    _prev_live_context_tokens: int = field(default=0, repr=False)
    _ema_live_context: float = field(default=0.0, repr=False)

    def update_live_context(self, new_tokens: int) -> None:
        self._prev_live_context_tokens = self.live_context_tokens
        self.live_context_tokens = new_tokens
        if self._ema_live_context == 0.0:
            self._ema_live_context = float(new_tokens)
        else:
            self._ema_live_context = EMA_ALPHA * new_tokens + (1 - EMA_ALPHA) * self._ema_live_context

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def context_window_known(self) -> bool:
        return lookup_context_window(self.model) is not None

    @property
    def context_window(self) -> int:
        return lookup_context_window(self.model) or DEFAULT_CONTEXT_WINDOW

    @property
    def effective_window(self) -> int:
        return effective_window(self.context_window)

    @property
    def usable_window(self) -> int:
        return self.effective_window - RESPONSE_RESERVE

    @property
    def raw_pressure(self) -> float:
        """Single-turn snapshot pressure, no smoothing."""
        return min(1.0, self.live_context_tokens / self.usable_window)

    @property
    def context_pressure(self) -> float:
        """EMA-smoothed pressure — use for scoring to reduce turn-to-turn volatility."""
        ema = self._ema_live_context if self._ema_live_context > 0 else float(self.live_context_tokens)
        return min(1.0, ema / self.usable_window)

    @property
    def confidence(self) -> Literal["high", "medium", "low"]:
        if not self.context_window_known:
            return "medium"
        prev = self._prev_live_context_tokens
        if prev > 0 and self.live_context_tokens < prev * (1 - COMPACTION_DROP_THRESHOLD):
            return "low"
        return "high"

    @property
    def context_pressure_score(self) -> float:
        return score_for_pressure(self.context_pressure)

    @property
    def status(self) -> Status:
        return status_for_score(self.context_pressure_score)

    @property
    def status_color(self) -> str:
        return STATUS_COLORS[self.status]
