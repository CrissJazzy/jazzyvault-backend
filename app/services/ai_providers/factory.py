from functools import lru_cache

from app.core.config import settings
from app.services.ai_providers.base import AIProvider, AIProviderError


@lru_cache
def get_ai_provider() -> AIProvider:
    """
    Returns the active AI provider based on the AI_PROVIDER environment
    variable. This is the ONLY place in the application that branches on
    which provider is configured — every caller (app/services/ai_service.py)
    just calls .generate() against whatever this returns, so switching
    providers is purely an environment variable change with zero code
    changes elsewhere, per the project's AI architecture requirement.
    """
    provider = settings.AI_PROVIDER

    if provider == "gemini":
        from app.services.ai_providers.gemini import GeminiProvider

        return GeminiProvider()

    if provider == "openai":
        from app.services.ai_providers.openai_provider import OpenAIProvider

        return OpenAIProvider()

    if provider == "groq":
        from app.services.ai_providers.groq_provider import GroqProvider

        return GroqProvider()

    raise AIProviderError(
        f"Unknown AI_PROVIDER '{provider}'. Must be one of: gemini, openai, groq."
    )
