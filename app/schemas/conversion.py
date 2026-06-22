from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.core.validators import UUID_PATTERN


class ConversionStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


# Supported conversion pairs, per project spec.
SUPPORTED_CONVERSIONS: dict[str, set[str]] = {
    "docx": {"pdf"},
    "pdf": {"docx", "jpg", "png"},
    "jpg": {"pdf"},
    "jpeg": {"pdf"},
    "png": {"pdf"},
}

_ALL_TARGET_FORMATS = sorted(
    {fmt for targets in SUPPORTED_CONVERSIONS.values() for fmt in targets}
)


class ConvertRequest(BaseModel):
    file_id: str = Field(pattern=UUID_PATTERN)
    target_format: str

    @field_validator("target_format")
    @classmethod
    def validate_target_format(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in _ALL_TARGET_FORMATS:
            raise ValueError(
                f"target_format must be one of: {', '.join(_ALL_TARGET_FORMATS)}"
            )
        return normalized


class ConversionResponse(BaseModel):
    id: str
    user_id: str
    input_file_id: str
    output_file_id: str | None
    input_format: str
    output_format: str
    status: ConversionStatus
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ConversionListResponse(BaseModel):
    conversions: list[ConversionResponse]
    total: int


# --- Phase 5: Conversion History -----------------------------------
# A richer view of a conversion for the dedicated History page, which
# the spec requires to show file name and file size alongside the
# fields already in ConversionResponse. Kept as a separate schema
# rather than changing ConversionResponse, since that one is also used
# by POST /convert and GET /convert/{id} from Phase 4 and shouldn't
# change shape under existing callers.
class ConversionHistoryEntry(BaseModel):
    id: str
    user_id: str
    input_file_id: str
    output_file_id: str | None
    file_name: str
    file_size: int
    input_format: str
    output_format: str
    status: ConversionStatus
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ConversionHistoryResponse(BaseModel):
    conversions: list[ConversionHistoryEntry]
    total: int
