from dotenv import load_dotenv
from meter import SessionStats
from providers import BaseProvider, get_provider

load_dotenv()


class ChatSession:
    def __init__(self, provider: BaseProvider = None, system: str = "You are a helpful assistant."):
        self.provider = provider or get_provider()
        self.system = system
        self.history: list[dict] = []
        self.stats = SessionStats(model=self.provider.model_id)

    def send(self, prompt: str) -> str:
        self.history.append({"role": "user", "content": prompt})

        response = self.provider.send(self.history, self.system)

        self.history.append({"role": "assistant", "content": response.text})

        self.stats.turns += 1
        self.stats.total_input_tokens += response.input_tokens
        self.stats.total_output_tokens += response.output_tokens
        self.stats.cache_read_tokens += response.cache_read_tokens
        self.stats.cache_creation_tokens += response.cache_creation_tokens
        effective_input = (response.input_tokens + response.cache_read_tokens
                           + response.cache_creation_tokens)
        self.stats.update_live_context(effective_input + response.output_tokens)

        return response.text

    def reset(self):
        self.history.clear()
        self.stats = SessionStats(model=self.provider.model_id)
