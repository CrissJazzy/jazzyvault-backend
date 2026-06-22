from fastapi import APIRouter, Depends, Query, Request

from app.core.limiter import limiter
from app.core.security import CurrentUser, get_current_user
from app.schemas.dashboard import ActivityFeedResponse
from app.services.dashboard_service import DashboardService

router = APIRouter()


@router.get("/recent", response_model=ActivityFeedResponse)
@limiter.limit("60/minute")
async def get_recent_activity(
    request: Request,
    limit: int = Query(default=20, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    return DashboardService.get_recent_activity(current_user.id, limit=limit)
