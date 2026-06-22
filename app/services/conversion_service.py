import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin
from app.schemas.conversion import SUPPORTED_CONVERSIONS, ConversionResponse
from app.services.conversion.image_converter import (
    ImageConversionError,
    image_to_pdf,
    pdf_to_images,
)
from app.services.conversion.libreoffice import ConversionError, convert_with_libreoffice
from app.services.activity_service import ActivityService
from app.services.file_service import FileService

logger = logging.getLogger(__name__)


def _validate_conversion(input_format: str, target_format: str) -> None:
    input_format = input_format.lower()
    target_format = target_format.lower()

    supported_targets = SUPPORTED_CONVERSIONS.get(input_format)
    if not supported_targets or target_format not in supported_targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Converting {input_format.upper()} to {target_format.upper()} "
                f"is not supported."
            ),
        )


class ConversionService:
    @staticmethod
    async def convert_file(
        user_id: str, file_id: str, target_format: str
    ) -> ConversionResponse:
        target_format = target_format.lower()
        admin = get_supabase_admin()

        # 1. Look up the source file and validate the conversion pair.
        source_file = FileService.get_file(user_id, file_id)
        _validate_conversion(source_file.file_type, target_format)

        # 2. Create the conversion record in 'pending' state immediately,
        #    so it shows up in history even if something fails downstream.
        conversion_row = (
            admin.table("conversions")
            .insert(
                {
                    "user_id": user_id,
                    "input_file_id": file_id,
                    "input_format": source_file.file_type,
                    "output_format": target_format,
                    "status": "processing",
                }
            )
            .execute()
        )
        if not conversion_row.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create conversion record.",
            )
        conversion_id = conversion_row.data[0]["id"]

        ActivityService.log(
            user_id=user_id,
            activity_type="conversion_started",
            description=(
                f"Converting \"{source_file.file_name}\" "
                f"({source_file.file_type.upper()} \u2192 {target_format.upper()})"
            ),
            metadata={
                "conversion_id": conversion_id,
                "input_file_id": file_id,
                "input_format": source_file.file_type,
                "output_format": target_format,
            },
        )

        try:
            output_file_id = await ConversionService._run_conversion(
                user_id=user_id,
                source_file=source_file,
                target_format=target_format,
            )
        except (ConversionError, ImageConversionError) as e:
            admin.table("conversions").update(
                {"status": "failed", "error_message": str(e)[:500]}
            ).eq("id", conversion_id).execute()
            ActivityService.log(
                user_id=user_id,
                activity_type="conversion_failed",
                description=(
                    f"Conversion of \"{source_file.file_name}\" failed"
                ),
                metadata={"conversion_id": conversion_id, "error": str(e)[:300]},
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Conversion failed: {e}",
            )
        except Exception as e:
            logger.exception("Unexpected conversion failure")
            admin.table("conversions").update(
                {"status": "failed", "error_message": "An unexpected error occurred."}
            ).eq("id", conversion_id).execute()
            ActivityService.log(
                user_id=user_id,
                activity_type="conversion_failed",
                description=(
                    f"Conversion of \"{source_file.file_name}\" failed unexpectedly"
                ),
                metadata={"conversion_id": conversion_id},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Conversion failed unexpectedly: {e}",
            )

        updated = (
            admin.table("conversions")
            .update(
                {
                    "status": "completed",
                    "output_file_id": output_file_id,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", conversion_id)
            .execute()
        )
        ActivityService.log(
            user_id=user_id,
            activity_type="conversion_completed",
            description=(
                f"Converted \"{source_file.file_name}\" to "
                f"{target_format.upper()}"
            ),
            metadata={
                "conversion_id": conversion_id,
                "output_file_id": output_file_id,
            },
        )
        return ConversionResponse(**updated.data[0])

    @staticmethod
    async def _run_conversion(user_id: str, source_file, target_format: str) -> str:
        """
        Downloads the source file, converts it, uploads the result, and
        returns the new file's ID. Multi-page PDF->image conversions
        produce multiple output files; only the first is linked as the
        conversion's primary output_file_id, but all pages are saved to
        the vault.
        """
        admin = get_supabase_admin()
        input_format = source_file.file_type.lower()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            input_path = tmp_dir / source_file.file_name

            # Download the source file's bytes from Storage.
            try:
                file_bytes = admin.storage.from_(
                    settings.SUPABASE_STORAGE_BUCKET
                ).download(source_file.storage_path)
            except Exception as e:
                raise ConversionError(f"Could not retrieve source file: {e}")

            input_path.write_bytes(file_bytes)

            output_paths: list[Path]

            if input_format == "docx" and target_format == "pdf":
                result = await convert_with_libreoffice(input_path, tmp_dir, "pdf")
                output_paths = [result]
            elif input_format == "pdf" and target_format == "docx":
                result = await convert_with_libreoffice(input_path, tmp_dir, "docx")
                output_paths = [result]
            elif input_format in ("jpg", "jpeg", "png") and target_format == "pdf":
                out_path = tmp_dir / f"{input_path.stem}.pdf"
                output_paths = [image_to_pdf(input_path, out_path)]
            elif input_format == "pdf" and target_format in ("jpg", "png"):
                output_paths = pdf_to_images(input_path, tmp_dir, fmt=target_format)
            else:
                raise ConversionError(
                    f"No converter implemented for {input_format} -> {target_format}."
                )

            # Upload each output file to Storage + create a `files` row,
            # exactly the same way a manual upload would, so converted
            # files appear in the Vault automatically.
            first_file_id: str | None = None
            for out_path in output_paths:
                file_id = ConversionService._save_output_file(
                    admin, user_id, out_path, target_format
                )
                if first_file_id is None:
                    first_file_id = file_id

            assert first_file_id is not None
            return first_file_id

    @staticmethod
    def _save_output_file(
        admin, user_id: str, local_path: Path, file_type: str
    ) -> str:
        contents = local_path.read_bytes()
        storage_path = f"{user_id}/{uuid.uuid4()}-{local_path.name}"

        admin.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            storage_path,
            contents,
            file_options={"content-type": _content_type_for(file_type)},
        )

        result = (
            admin.table("files")
            .insert(
                {
                    "user_id": user_id,
                    "file_name": local_path.name,
                    "storage_path": storage_path,
                    "file_url": storage_path,
                    "file_size": len(contents),
                    "file_type": file_type,
                }
            )
            .execute()
        )
        if not result.data:
            raise ConversionError("Failed to save the converted file record.")
        return result.data[0]["id"]


def _content_type_for(file_type: str) -> str:
    return {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
    }.get(file_type, "application/octet-stream")
