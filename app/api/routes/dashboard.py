from fastapi import APIRouter, Depends, Query, Request

from app.core.limiter import limiter
from app.core.security import CurrentUser, get_current_user
from app.schemas.dashboard import DashboardStats, GlobalSearchResponse
from app.services.dashboard_service import DashboardService

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
@limiter.limit("60/minute")
async def get_dashboard_stats(
    request: Request, current_user: CurrentUser = Depends(get_current_user)
):
    return DashboardService.get_stats(current_user.id)


@router.get("/search", response_model=GlobalSearchResponse)
@limiter.limit("30/minute")
async def global_search(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    current_user: CurrentUser = Depends(get_current_user),
):
    return DashboardService.global_search(current_user.id, q)
