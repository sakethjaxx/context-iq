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

# Logistic scoring curve: plateau 0-40%, noticeable 40-70%, sharp 70-90%, cliff 90%+
_SCORE_K = 14       # steepness — higher = sharper cliff
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
    # Live — approximated as last_input + last_output; use for health/pressure
    live_context_tokens: int = 0

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
    def context_pressure(self) -> float:
        return min(1.0, self.live_context_tokens / self.usable_window)

    @property
    def intelligence_score(self) -> float:
        """0–100. Logistic: plateau until ~40% pressure, cliff at 90%+."""
        raw = 1 / (1 + math.exp(_SCORE_K * (self.context_pressure - _SCORE_C)))
        return max(0.0, round(100 * (raw - _SCORE_LO) / (_SCORE_HI - _SCORE_LO), 1))

    @property
    def status(self) -> Literal["fresh", "warm", "strained", "critical"]:
        s = self.intelligence_score
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
