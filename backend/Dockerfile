FROM ghcr.io/astral-sh/uv:0.7.19 AS uv

FROM python:3.12.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

USER appuser

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "xuemian_ai.main:app", "--host", "0.0.0.0", "--port", "8000"]

