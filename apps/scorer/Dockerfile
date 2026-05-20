FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# The api package is mounted/copied alongside the scorer for shared models.
COPY apps/api /app/apps/api
COPY apps/scorer /app/apps/scorer

RUN pip install --upgrade pip \
    && pip install -e /app/apps/api \
    && pip install -e /app/apps/scorer

WORKDIR /app/apps/scorer

CMD ["python", "-m", "cellbench_scorer.worker"]
