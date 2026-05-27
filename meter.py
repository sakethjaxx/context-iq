import math
from dataclasses import dataclass, field
from typing import Literal

MODEL_CONTEXT_WINDOWS = {
    # Claude
    "claude-opus-4-7": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
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

# Logistic scoring curve: plateau 0-40%, noticeable 40-70%, sharp 70-90%, cliff 90%+
_SCORE_K = 14       # steepness
_SCORE_C = 0.78     # inflection point (78% pressure)
_SCORE_LO = 1 / (1 + math.exp(_SCORE_K * (1.0 - _SCORE_C)))
_SCORE_HI = 1 / (1 + math.exp(_SCORE_K * (0.0 - _SCORE_C)))


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
        return self.model in MODEL_CONTEXT_WINDOWS

    @property
    def context_window(self) -> int:
        return MODEL_CONTEXT_WINDOWS.get(self.model, DEFAULT_CONTEXT_WINDOW)

    @property
    def usable_window(self) -> int:
        return self.context_window - RESPONSE_RESERVE

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
        """0-100. Logistic: plateau until ~40% pressure, cliff at 90%+."""
        raw = 1 / (1 + math.exp(_SCORE_K * (self.context_pressure - _SCORE_C)))
        return max(0.0, round(100 * (raw - _SCORE_LO) / (_SCORE_HI - _SCORE_LO), 1))

    @property
    def status(self) -> Literal["fresh", "warm", "strained", "critical"]:
        s = self.context_pressure_score
        if s >= 70:
            return "fresh"
        elif s >= 40:
            return "warm"
        elif s >= 15:
            return "strained"
        return "critical"

    @property
    def status_color(self) -> str:
        return {
            "fresh": "green",
            "warm": "yellow",
            "strained": "orange3",
            "critical": "red",
        }[self.status]
