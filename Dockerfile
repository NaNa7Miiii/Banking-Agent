# syntax=docker/dockerfile:1.6
# ---------- Banking Agent container ----------
# Single-stage slim image. Runs the FastAPI server; the LangGraph runtime is
# built lazily on the first /api/chat call so the image builds without secrets
# and /healthz comes up fast for Railway.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# System deps: libpq for psycopg2, build-essential only while installing wheels,
# then purged to keep the image small.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt \
 && apt-get purge -y --auto-remove build-essential \
 && rm -rf /root/.cache /var/lib/apt/lists/*

# Copy only runtime assets (see .dockerignore for the exclude list).
COPY src ./src
COPY fraud_detection/ml_model ./fraud_detection/ml_model
COPY resources ./resources

# Non-root user for defence-in-depth.
RUN useradd --create-home --uid 1001 app \
 && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT}/healthz || exit 1

# Shell form so ${PORT} (set by Railway) is expanded at runtime.
CMD uvicorn src.server.app:app --host 0.0.0.0 --port ${PORT}
