from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class ProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    avatar_url: str | None = None
    storage_used_bytes: int
    storage_limit_bytes: int
    created_at: datetime
    updated_at: datetime


class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: int | None = None
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    user: ProfileResponse
    session: SessionResponse


class MessageResponse(BaseModel):
    message: str
