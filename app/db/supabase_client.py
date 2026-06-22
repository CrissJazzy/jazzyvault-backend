from functools import lru_cache

from supabase import Client, create_client

from app.core.config import settings


@lru_cache
def get_supabase_admin() -> Client:
    """
    Service-role client. Bypasses Row Level Security.
    Use ONLY for trusted server-side operations (e.g. storage writes
    after the request's JWT has already been verified).
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


@lru_cache
def get_supabase_anon() -> Client:
    """
    Anon-role client. Respects Row Level Security.
    Use for operations that should be scoped to the requesting user.
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
