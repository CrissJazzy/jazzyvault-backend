from fastapi import APIRouter, Depends, Header, Request, status

from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import CurrentUser, get_current_user
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    PasswordResetRequest,
    ProfileResponse,
    RegisterRequest,
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(request: Request, payload: RegisterRequest):
    return AuthService.register(payload)


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest):
    return AuthService.login(payload)


@router.post("/logout", response_model=MessageResponse)
@limiter.limit("20/minute")
async def logout(request: Request, authorization: str | None = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        AuthService.logout(token)
    return MessageResponse(message="Logged out successfully.")


@router.post("/password-reset", response_model=MessageResponse)
@limiter.limit("5/minute")
async def request_password_reset(request: Request, payload: PasswordResetRequest):
    redirect_to = f"{settings.FRONTEND_URL}/reset-password"
    AuthService.request_password_reset(payload.email, redirect_to)
    # Always return the same response regardless of whether the email
    # exists, to avoid account enumeration.
    return MessageResponse(
        message="If an account exists for that email, a password reset link has been sent."
    )


@router.get("/me", response_model=ProfileResponse)
@limiter.limit("60/minute")
async def get_me(request: Request, current_user: CurrentUser = Depends(get_current_user)):
    return AuthService.get_profile(current_user.id)
