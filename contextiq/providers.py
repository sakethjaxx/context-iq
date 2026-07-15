import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

MAX_TOKENS = 8192


@dataclass
class ProviderResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


class BaseProvider(ABC):
    @abstractmethod
    def send(self, messages: list, system: str) -> ProviderResponse:
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

    def send(self, messages: list, system: str) -> ProviderResponse:
        full_messages = [{"role": "system", "content": system}] + messages
        response = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            max_tokens=MAX_TOKENS,
        )
        usage = response.usage
        return ProviderResponse(
            text=response.choices[0].message.content,
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

    def send(self, messages: list, system: str) -> ProviderResponse:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
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


class OpenAICompatProvider(BaseProvider):
    """Any OpenAI-compatible endpoint: OpenAI, Ollama, LM Studio, OpenRouter, vLLM.

    Configure with OPENAI_BASE_URL + OPENAI_API_KEY + OPENAI_MODEL, e.g.
      Ollama:    OPENAI_BASE_URL=http://localhost:11434/v1  OPENAI_API_KEY=ollama
      LM Studio: OPENAI_BASE_URL=http://localhost:1234/v1   OPENAI_API_KEY=lmstudio
      OpenRouter: OPENAI_BASE_URL=https://openrouter.ai/api/v1
    """
    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, api_key: str = None, model: str = None, base_url: str = None):
        from openai import OpenAI
        self._model = model or os.getenv("OPENAI_MODEL", self.DEFAULT_MODEL)
        self._client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=base_url or os.getenv("OPENAI_BASE_URL") or None,
        )

    @property
    def model_id(self) -> str:
        return self._model

    def send(self, messages: list, system: str) -> ProviderResponse:
        full_messages = [{"role": "system", "content": system}] + messages
        response = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            max_tokens=MAX_TOKENS,
        )
        usage = response.usage
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0 if details else 0
        return ProviderResponse(
            text=response.choices[0].message.content,
            input_tokens=usage.prompt_tokens - cached,
            output_tokens=usage.completion_tokens,
            cache_read_tokens=cached,
        )


PROVIDERS = {
    "groq": GroqProvider,
    "claude": ClaudeProvider,
    "openai": OpenAICompatProvider,
    "ollama": lambda: OpenAICompatProvider(
        api_key=os.getenv("OPENAI_API_KEY", "ollama"),
        base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        model=os.getenv("OPENAI_MODEL", "llama3.2"),
    ),
}


def get_provider() -> BaseProvider:
    """Instantiate provider from PROVIDER env var. Defaults to groq."""
    provider = os.getenv("PROVIDER", "groq").lower()
    factory = PROVIDERS.get(provider)
    if factory is None:
        raise ValueError(f"Unknown provider: {provider}. Supported: {', '.join(PROVIDERS)}")
    return factory()
