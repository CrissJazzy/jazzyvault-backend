from openai import AsyncOpenAI, APIError

from app.core.config import settings
from app.services.ai_providers.base import AIProvider, AIProviderError


class OpenAIProvider(AIProvider):
    """
    OpenAI provider — secondary/future provider per the project spec.
    Not the default (Gemini is), but implements the same AIProvider
    interface so switching AI_PROVIDER=openai requires no other code
    changes anywhere in the application.
    """

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise AIProviderError(
                "OPENAI_API_KEY is not configured. Set it in your environment "
                "to use the OpenAI AI provider."
            )
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_MODEL

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
                max_tokens=max_output_tokens,
                temperature=temperature,
            )
        except APIError as e:
            raise AIProviderError(f"OpenAI request failed: {e}")
        except Exception as e:
            raise AIProviderError(f"Unexpected error calling OpenAI: {e}")

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise AIProviderError("OpenAI returned an empty response.")
        return content
