# Build context is the repo root, so the image can include migrations/.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app/backend
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/src ./src
COPY migrations /app/migrations
RUN uv sync --frozen --no-dev

ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "apexrep.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
