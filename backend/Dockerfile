# Build context is the repository root so the image can carry data/ (corpus, configs, golden set).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

COPY backend/pyproject.toml backend/requirements.lock ./
RUN mkdir -p src/retrieval_lab && touch src/retrieval_lab/__init__.py \
    && pip install -c requirements.lock -e . \
    && rm -rf src

COPY backend/ ./
COPY data/ /app/data/
RUN pip install --no-deps -e . \
    && useradd --create-home --uid 10001 rlab \
    && mkdir -p /app/.local/models && chown -R rlab /app/.local /app/data/baselines

USER rlab
EXPOSE 8102

HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8102/api/health')"

CMD ["sh", "-c", "rlab db upgrade && uvicorn retrieval_lab.api.app:app --host 0.0.0.0 --port 8102"]
