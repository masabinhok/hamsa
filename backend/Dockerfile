# The API, worker and corpus watcher share this image. Build from the repo root:
#   docker compose build
FROM python:3.12-slim

# ffmpeg: yt-dlp cuts and merges downloads with it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv

WORKDIR /app/backend
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY backend/pyproject.toml backend/uv.lock ./
# The download cache lives in a build cache mount, not in the image (it doubled its size).
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev \
    # yt-dlp is called as a program, not imported, so it is not a project dependency.
    && uv pip install --python .venv/bin/python yt-dlp==2026.8.19

ENV PATH="/app/backend/.venv/bin:$PATH"
