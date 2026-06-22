# JazzyVault Backend — Dockerfile
#
# Render's native Python runtime cannot install LibreOffice (no apt
# access during build), which is required for DOCX<->PDF conversion.
# Docker deployment is the documented, reliable path on Render's free
# tier for this — see README "Phase 4 — Why Docker" for the full
# explanation.

FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- System dependencies ---
# - libreoffice: DOCX <-> PDF conversion (headless, via the `soffice` CLI)
# - poppler-utils: PDF <-> image conversion (used by pdf2image)
# - fonts: improves DOCX->PDF rendering fidelity for common documents
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    poppler-utils \
    fonts-dejavu \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render injects $PORT at runtime; default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

# --proxy-headers tells Uvicorn to trust X-Forwarded-For/X-Forwarded-Proto
# from the immediate upstream proxy and use it to populate
# request.client.host with the real client IP. Render (like most PaaS)
# terminates TLS and proxies to this container, so without this flag
# every request would appear to originate from Render's internal proxy
# IP, making slowapi's IP-based rate limiting (app/core/limiter.py)
# effectively useless in production — see Phase 8 README section.
# --forwarded-allow-ips='*' trusts the immediate hop, which is safe here
# specifically because Render's edge is the only thing that can reach
# this container directly (it isn't exposed to the raw internet).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
