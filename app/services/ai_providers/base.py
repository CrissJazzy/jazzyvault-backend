from abc import ABC, abstractmethod


class AIProviderError(Exception):
    """Raised when an AI provider call fails for any reason (network,
    auth, rate limit, content policy, etc.) — callers shouldn't need to
    know which provider is active to handle errors uniformly."""

    pass


class AIProvider(ABC):
    """
    Provider-agnostic interface for text-generation AI calls. Every
    provider (Gemini, OpenAI, Groq, ...) implements this same shape, so
    app/services/ai_service.py never needs to know which one is active —
    switching is purely an AI_PROVIDER environment variable change.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_output_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """
        Sends a single-turn prompt to the model and returns the text
        response. Raises AIProviderError on any failure.
        """
        raise NotImplementedError
