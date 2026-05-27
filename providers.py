import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProviderResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


class BaseProvider(ABC):
    @abstractmethod
    def send(self, messages: list[dict], system: str) -> ProviderResponse:
        pass

    @property
    @abstractmethod
    def model_id(self) -> str:
        pass


class GroqProvider(BaseProvider):
    DEFAULT_MODEL = "llama-3.3-70b-versatile"

    def __init__(self, api_key: str = None, model: str = None):
        from groq import Groq
        self._model = model or os.getenv("GROQ_MODEL", self.DEFAULT_MODEL)
        self._client = Groq(api_key=api_key or os.getenv("GROQ_API_KEY"))

    @property
    def model_id(self) -> str:
        return self._model

    def send(self, messages: list[dict], system: str) -> ProviderResponse:
        full_messages = [{"role": "system", "content": system}] + messages
        response = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            max_tokens=8096,
        )
        choice = response.choices[0].message.content
        usage = response.usage
        return ProviderResponse(
            text=choice,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )


class ClaudeProvider(BaseProvider):
    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, api_key: str = None, model: str = None):
        from anthropic import Anthropic
        self._model = model or os.getenv("ANTHROPIC_MODEL", self.DEFAULT_MODEL)
        self._client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    @property
    def model_id(self) -> str:
        return self._model

    def send(self, messages: list[dict], system: str) -> ProviderResponse:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=8096,
            system=system,
            messages=messages,
        )
        usage = response.usage
        return ProviderResponse(
            text=response.content[0].text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )


def get_provider() -> BaseProvider:
    """Instantiate provider from PROVIDER env var. Defaults to groq."""
    provider = os.getenv("PROVIDER", "groq").lower()
    if provider == "groq":
        return GroqProvider()
    elif provider == "claude":
        return ClaudeProvider()
    else:
        raise ValueError(f"Unknown provider: {provider}. Supported: groq, claude")
