from groq import AsyncGroq, APIError

from app.core.config import settings
from app.services.ai_providers.base import AIProvider, AIProviderError


class GroqProvider(AIProvider):
    """
    Groq provider — secondary/future provider per the project spec.
    Groq's API is OpenAI-compatible in shape, with one notable
    difference: it uses `max_completion_tokens` instead of `max_tokens`.
    """

    def __init__(self) -> None:
        if not settings.GROQ_API_KEY:
            raise AIProviderError(
                "GROQ_API_KEY is not configured. Set it in your environment "
                "to use the Groq AI provider."
            )
        self._client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self._model = settings.GROQ_MODEL

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_output_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_completion_tokens=max_output_tokens,
                temperature=temperature,
            )
        except APIError as e:
            raise AIProviderError(f"Groq request failed: {e}")
        except Exception as e:
            raise AIProviderError(f"Unexpected error calling Groq: {e}")

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise AIProviderError("Groq returned an empty response.")
        return content
