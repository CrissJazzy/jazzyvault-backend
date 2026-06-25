self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
self._model = settings.GEMINI_MODEL

print("GEMINI MODEL:", self._model)
