from dataclasses import dataclass
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


@dataclass
class SessionStats:
    model: str
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def context_window(self) -> int:
        return MODEL_CONTEXT_WINDOWS.get(self.model, DEFAULT_CONTEXT_WINDOW)

    @property
    def context_pressure(self) -> float:
        return min(1.0, self.input_tokens / self.context_window)

    @property
    def intelligence_score(self) -> float:
        """0–100. Non-linear decay — feels fine until ~50%, then drops fast."""
        p = self.context_pressure
        if p < 0.3:
            score = 100 - (p / 0.3) * 20        # 100 → 80
        elif p < 0.6:
            score = 80 - ((p - 0.3) / 0.3) * 30  # 80 → 50
        elif p < 0.85:
            score = 50 - ((p - 0.6) / 0.25) * 35 # 50 → 15
        else:
            score = 15 - ((p - 0.85) / 0.15) * 15 # 15 → 0
        return max(0.0, round(score, 1))

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
