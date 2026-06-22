from fastapi import HTTPException, status
from gotrue.errors import AuthApiError

from app.db.supabase_client import get_supabase_admin, get_supabase_anon
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    ProfileResponse,
    RegisterRequest,
    SessionResponse,
)


def _session_to_schema(session) -> SessionResponse:
    # Built defensively: the GoTrue Session object's exact attribute set can
    # vary slightly between supabase-py versions. getattr() with fallbacks
    # avoids a hard crash if a field is named or typed differently than
    # expected — verify against your installed supabase-py version's
    # Session model if you see unexpected nulls here.
    return SessionResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=getattr(session, "expires_in", 3600),
        expires_at=getattr(session, "expires_at", None),
        token_type=getattr(session, "token_type", "bearer"),
    )


def _fetch_profile(user_id: str) -> ProfileResponse:
    admin = get_supabase_admin()
    result = (
        admin.table("profiles").select("*").eq("id", user_id).single().execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. It may still be provisioning — try again shortly.",
        )
    return ProfileResponse(**result.data)


class AuthService:
    @staticmethod
    def register(payload: RegisterRequest) -> AuthResponse:
        anon = get_supabase_anon()
        try:
            result = anon.auth.sign_up(
                {
                    "email": payload.email,
                    "password": payload.password,
                    "options": {"data": {"full_name": payload.full_name}},
                }
            )
        except AuthApiError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

        if not result.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration failed. Please try again.",
            )

        if not result.session:
            # Email confirmation is required before a session is issued.
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail="Registration successful. Please check your email to confirm your account before logging in.",
            )

        profile = _fetch_profile(result.user.id)
        return AuthResponse(user=profile, session=_session_to_schema(result.session))

    @staticmethod
    def login(payload: LoginRequest) -> AuthResponse:
        anon = get_supabase_anon()
        try:
            result = anon.auth.sign_in_with_password(
                {"email": payload.email, "password": payload.password}
            )
        except AuthApiError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        if not result.user or not result.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        profile = _fetch_profile(result.user.id)
        return AuthResponse(user=profile, session=_session_to_schema(result.session))

    @staticmethod
    def logout(access_token: str) -> None:
        anon = get_supabase_anon()
        try:
            anon.auth.sign_out(access_token)
        except AuthApiError:
            # Sign-out is best-effort; an already-expired token isn't an error case
            # worth surfacing to the client.
            pass

    @staticmethod
    def request_password_reset(email: str, redirect_to: str) -> None:
        anon = get_supabase_anon()
        try:
            anon.auth.reset_password_for_email(email, {"redirect_to": redirect_to})
        except AuthApiError:
            # Intentionally swallow errors here too — never reveal whether
            # an email address is registered (standard practice to avoid
            # account enumeration).
            pass

    @staticmethod
    def get_profile(user_id: str) -> ProfileResponse:
        return _fetch_profile(user_id)
