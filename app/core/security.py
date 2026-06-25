from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.services.supabase import supabase

bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    id: str
    email: str | None = None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:

    print("AUTH HEADER:", credentials)

    if credentials is None:
        print("NO TOKEN RECEIVED")
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token",
        )

    token = credentials.credentials

    print("TOKEN RECEIVED:", token[:30])

    try:
        response = supabase.auth.get_user(token)

        if not response.user:
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
            )

        return CurrentUser(
            id=response.user.id,
            email=response.user.email,
        )

    except Exception as e:
        print("AUTH ERROR:", str(e))

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token",
        )
