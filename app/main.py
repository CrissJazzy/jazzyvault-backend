from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import activity, ai, auth, conversion, dashboard, files
from app.core.config import settings
from app.core.limiter import limiter
from app.core.security_headers import SecurityHeadersMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    description="Secure AI-powered document vault — API",
    version="0.1.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware order: Starlette wraps each added middleware around the
# previous stack ("onion" model) — the LAST one added via add_middleware()
# becomes the OUTERMOST layer, seeing the request first and the response
# last. Adding SecurityHeadersMiddleware after CORSMiddleware means it
# wraps CORS, so its response-side header additions run after CORS has
# already set its own headers — both end up present on every response,
# including preflight (OPTIONS) responses. (Verified against Starlette's
# actual middleware-stack-building source, not assumed.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    # Narrowed from "*" to the methods this API actually exposes across
    # every route — avoids advertising support for methods (PUT, PATCH,
    # TRACE, CONNECT, ...) that no endpoint implements.
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    # Authorization (Bearer JWT) and Content-Type (JSON + multipart
    # uploads) are the only headers any client legitimately needs to
    # send to this API.
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(SecurityHeadersMiddleware)


@app.get("/")
async def root():
    return {
        "name": "JazzyVault API",
        "status": "online",
        "tagline": "Convert. Store. Secure. Smarter.",
    }


@app.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request):
    return JSONResponse(
        content={"status": "healthy", "environment": settings.ENVIRONMENT}
    )


app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(files.router, prefix="/files", tags=["Files"])
app.include_router(conversion.router, prefix="/convert", tags=["Conversion"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(activity.router, prefix="/activity", tags=["Activity"])
app.include_router(ai.router, prefix="/ai", tags=["AI"])
