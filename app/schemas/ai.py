from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.core.validators import UUID_PATTERN


class AIRequestType(str, Enum):
    summarize = "summarize"
    insights = "insights"
    simplify = "simplify"
    translate = "translate"
    analyze = "analyze"


class AIRequestStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class AIActionRequest(BaseModel):
    file_id: str = Field(pattern=UUID_PATTERN)
    # Only used by 'translate' — the target language, e.g. "Spanish" or "fr".
    target_language: str | None = Field(default=None, min_length=1, max_length=50)


class AIRequestResponse(BaseModel):
    id: str
    user_id: str
    file_id: str
    request_type: AIRequestType
    input_params: dict
    response: str | None
    status: AIRequestStatus
    error_message: str | None = None
    ai_provider: str
    created_at: datetime
    completed_at: datetime | None = None


class AIRequestListResponse(BaseModel):
    requests: list[AIRequestResponse]
    total: int
