# ---- EcoTwin AI :: backend -------------------------------------------------
# One image serves both deployment targets. Local engineering mode adds a
# BOPTEST service alongside it via docker-compose; the hosted demo runs this
# image alone and the Control Lab falls back to the EcoTwin RC engine, which
# the UI states explicitly rather than hiding.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libgomp is required by LightGBM; the rest of the stack is manylinux wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so a code change does not invalidate the wheel layer.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY core/ ./core/
COPY apps/api/ ./apps/api/
COPY scripts/ ./scripts/
COPY pyproject.toml ./

# Prepared data and trained models are baked in: the hosted demo must never
# train, download or preprocess anything while someone is watching.
COPY data/processed/ ./data/processed/
COPY models/ ./models/
COPY demo/ ./demo/

# Run unprivileged.
RUN useradd --create-home --uid 10001 ecotwin && chown -R ecotwin:ecotwin /app
USER ecotwin

ENV ECOTWIN_ROOT=/app \
    ECOTWIN_DEMO_MODE=true \
    ECOTWIN_INTERVIEW_MODE=true \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# Single worker on purpose: the services hold warmed per-asset caches, and a
# second worker would double the memory for no throughput a demo needs.
CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
