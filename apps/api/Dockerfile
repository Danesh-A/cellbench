# Build context is the repo root so we can install both api and scorer.
# See docker-compose.yml: build.context=.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install both packages: api owns the HTTP surface, scorer owns the
# scoring math (which the baseline_submissions and fetch scripts also
# import). One container, one venv, two editable installs.
COPY apps/api /app/apps/api
COPY apps/scorer /app/apps/scorer

RUN pip install --upgrade pip \
    && pip install -e /app/apps/api[dev] \
    && pip install -e /app/apps/scorer

WORKDIR /app/apps/api

EXPOSE 8000

CMD ["uvicorn", "cellbench_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
