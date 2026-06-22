from fastapi import APIRouter, Depends, Path, Query, Request

from app.core.limiter import limiter
from app.core.security import CurrentUser, get_current_user
from app.core.validators import UUID_PATTERN
from app.schemas.ai import AIActionRequest, AIRequestListResponse, AIRequestResponse
from app.services.ai_service import AIService

router = APIRouter()


@router.post("/summarize", response_model=AIRequestResponse)
@limiter.limit("15/minute")
async def summarize(
    request: Request,
    payload: AIActionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await AIService.run_request(current_user.id, payload.file_id, "summarize")


@router.post("/insights", response_model=AIRequestResponse)
@limiter.limit("15/minute")
async def insights(
    request: Request,
    payload: AIActionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await AIService.run_request(current_user.id, payload.file_id, "insights")


@router.post("/simplify", response_model=AIRequestResponse)
@limiter.limit("15/minute")
async def simplify(
    request: Request,
    payload: AIActionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await AIService.run_request(current_user.id, payload.file_id, "simplify")


@router.post("/translate", response_model=AIRequestResponse)
@limiter.limit("15/minute")
async def translate(
    request: Request,
    payload: AIActionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await AIService.run_request(
        current_user.id, payload.file_id, "translate", payload.target_language
    )


@router.post("/analyze", response_model=AIRequestResponse)
@limiter.limit("15/minute")
async def analyze(
    request: Request,
    payload: AIActionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await AIService.run_request(current_user.id, payload.file_id, "analyze")


@router.get("/history", response_model=AIRequestListResponse)
@limiter.limit("60/minute")
async def get_ai_history(
    request: Request,
    limit: int = Query(default=50, le=200),
    current_user: CurrentUser = Depends(get_current_user),
):
    requests = AIService.list_requests(current_user.id, limit=limit)
    return AIRequestListResponse(requests=requests, total=len(requests))


@router.get("/{request_id}", response_model=AIRequestResponse)
@limiter.limit("60/minute")
async def get_ai_request(
    request: Request,
    request_id: str = Path(pattern=UUID_PATTERN),
    current_user: CurrentUser = Depends(get_current_user),
):
    return AIService.get_request(current_user.id, request_id)
