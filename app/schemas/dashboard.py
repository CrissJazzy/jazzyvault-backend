from datetime import datetime

from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_files: int
    total_conversions: int
    successful_conversions: int
    failed_conversions: int
    storage_used_bytes: int
    storage_limit_bytes: int


class ActivityLogEntry(BaseModel):
    id: str
    user_id: str
    activity_type: str
    description: str
    metadata: dict
    created_at: datetime


class ActivityFeedResponse(BaseModel):
    activities: list[ActivityLogEntry]
    total: int


# --- Phase 7: Global Search -----------------------------------------

class SearchResultType(BaseModel):
    type: str  # "file" | "conversion" | "ai_request"
    id: str
    title: str
    subtitle: str
    created_at: datetime
    # Route the frontend should navigate to when this result is clicked.
    link: str


class GlobalSearchResponse(BaseModel):
    results: list[SearchResultType]
    total: int
