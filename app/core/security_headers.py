from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds standard security response headers to every API response. The
    frontend (Netlify) already sets equivalent headers for the pages it
    serves (see jazzyvault-frontend/netlify.toml), but this API is a
    separate origin and previously sent none of its own — a browser
    consuming this API directly, or an attacker probing it, saw no
    hardening at all. None of these are exotic; they're the standard
    baseline FastAPI/Starlette deployments are expected to set
    themselves, since the framework doesn't apply them by default.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        # Only meaningful over HTTPS, which is how this API is always
        # reached in production (Render terminates TLS at the edge).
        # Harmless to send over local HTTP dev too — browsers simply
        # ignore it on non-HTTPS origins.
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
        return response
