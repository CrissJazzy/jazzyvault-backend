from google import genai
from google.genai import errors, types

from app.core.config import settings
from app.services.ai_providers.base import AIProvider, AIProviderError


class GeminiProvider(AIProvider):
    """
    Google Gemini provider — the default/primary AI provider per the
    project spec (generous free tier, ideal for MVP).

    Uses the current `google-genai` SDK. NOTE: the older
    `google-generativeai` package (genai.configure() + GenerativeModel())
    reached end-of-life on Aug 31, 2025 and must not be used — this was
    caught and corrected during Phase 6 implementation; see the backend
    README's Phase 6 section for details.
    """

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise AIProviderError(
                "GEMINI_API_KEY is not configured. Set it in your environment "
                "to use the Gemini AI provider."
            )
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = settings.GEMINI_MODEL

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_output_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )

        try:
            # The SDK's async surface lives under client.aio — see
            # "Generate Content (Asynchronous Non Streaming)" in the
            # google-genai docs.
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
        except errors.APIError as e:
            raise AIProviderError(f"Gemini request failed: {e}")
        except Exception as e:
            raise AIProviderError(f"Unexpected error calling Gemini: {e}")

        text = getattr(response, "text", None)
        if not text:
            raise AIProviderError(
                "Gemini returned an empty response. The content may have "
                "been blocked by safety filters."
            )
        return text
