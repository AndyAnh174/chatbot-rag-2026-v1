# ── Stage 1: base ─────────────────────────────────────────────────────────
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: dev ──────────────────────────────────────────────────────────
# Code is bind-mounted via docker-compose volume for hot reload
FROM base AS dev

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ── Stage 3: prod ─────────────────────────────────────────────────────────
FROM base AS prod

COPY . .

RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["uvicorn", "config.asgi:application", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--log-level", "info"]
