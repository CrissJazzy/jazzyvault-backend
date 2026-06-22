import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin
from app.schemas.ai import AIRequestResponse
from app.services.activity_service import ActivityService
from app.services.ai_providers.factory import get_ai_provider
from app.services.ai_providers.base import AIProviderError
from app.services.ai_providers.prompts import SYSTEM_INSTRUCTION, build_prompt
from app.services.ai_providers.text_extraction import TextExtractionError, extract_text
from app.services.file_service import FileService

# Supported file types for AI document intelligence, per project spec
# scope. Images (jpg/png/pptx/xlsx) aren't text-extractable with the
# tools in this MVP — see README for what it would take to add them.
SUPPORTED_AI_FILE_TYPES = {"docx", "pdf", "txt"}


class AIService:
    @staticmethod
    async def run_request(
        user_id: str,
        file_id: str,
        request_type: str,
        target_language: str | None = None,
    ) -> AIRequestResponse:
        admin = get_supabase_admin()

        # 1. Look up the file and validate it's a supported type.
        file = FileService.get_file(user_id, file_id)
        if file.file_type.lower() not in SUPPORTED_AI_FILE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"AI document intelligence doesn't support "
                    f"'{file.file_type.upper()}' files yet. Supported: "
                    f"{', '.join(t.upper() for t in sorted(SUPPORTED_AI_FILE_TYPES))}."
                ),
            )

        if request_type == "translate" and not target_language:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A target_language is required for translation requests.",
            )

        # 2. Create the request record in 'processing' state immediately,
        #    mirroring the pattern from conversion_service.py (Phase 4).
        input_params = {"target_language": target_language} if target_language else {}
        request_row = (
            admin.table("ai_requests")
            .insert(
                {
                    "user_id": user_id,
                    "file_id": file_id,
                    "request_type": request_type,
                    "input_params": input_params,
                    "status": "processing",
                    "ai_provider": settings.AI_PROVIDER,
                }
            )
            .execute()
        )
        if not request_row.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create AI request record.",
            )
        request_id = request_row.data[0]["id"]

        ActivityService.log(
            user_id=user_id,
            activity_type="ai_request",
            description=f"Running {request_type} on \"{file.file_name}\"",
            metadata={"ai_request_id": request_id, "request_type": request_type},
        )

        # 3. Download, extract text, prompt the active provider.
        try:
            response_text = await AIService._execute(
                file, request_type, target_language
            )
        except (TextExtractionError, AIProviderError) as e:
            admin.table("ai_requests").update(
                {"status": "failed", "error_message": str(e)[:500]}
            ).eq("id", request_id).execute()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e),
            )
        except Exception as e:
            admin.table("ai_requests").update(
                {"status": "failed", "error_message": "An unexpected error occurred."}
            ).eq("id", request_id).execute()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI request failed unexpectedly: {e}",
            )

        # 4. Persist the result.
        updated = (
            admin.table("ai_requests")
            .update(
                {
                    "status": "completed",
                    "response": response_text,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", request_id)
            .execute()
        )
        return AIRequestResponse(**updated.data[0])

    @staticmethod
    async def _execute(file, request_type: str, target_language: str | None) -> str:
        admin = get_supabase_admin()

        with tempfile.TemporaryDirectory() as tmp:
            local_path = Path(tmp) / file.file_name
            try:
                file_bytes = admin.storage.from_(
                    settings.SUPABASE_STORAGE_BUCKET
                ).download(file.storage_path)
            except Exception as e:
                raise AIProviderError(f"Could not retrieve the file: {e}")

            local_path.write_bytes(file_bytes)
            document_text = extract_text(local_path, file.file_type)

        prompt = build_prompt(request_type, document_text, target_language)
        provider = get_ai_provider()
        return await provider.generate(
            prompt=prompt,
            system_instruction=SYSTEM_INSTRUCTION,
            max_output_tokens=2048,
            temperature=0.3,
        )

    @staticmethod
    def list_requests(user_id: str, limit: int = 50) -> list[AIRequestResponse]:
        admin = get_supabase_admin()
        result = (
            admin.table("ai_requests")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [AIRequestResponse(**row) for row in result.data]

    @staticmethod
    def get_request(user_id: str, request_id: str) -> AIRequestResponse:
        admin = get_supabase_admin()
        result = (
            admin.table("ai_requests")
            .select("*")
            .eq("id", request_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="AI request not found."
            )
        return AIRequestResponse(**result.data)
