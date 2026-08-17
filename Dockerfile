# ---------------------------------------------------------------------------
# Base — shared layer: Python 3.12, git, uv, and project dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

# Install git (required by both scripts) and curl for uv installer
RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy only the dependency spec first → cacheable install layer
COPY pyproject.toml uv.lock ./

# Install project dependencies into a separate location
# (frozen = uv.lock only, no network needed, --all-extras includes dev deps)
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"
RUN uv sync --frozen --compile-bytecode --all-extras --python-preference only-managed
ENV PATH="/opt/venv/bin:$PATH"
# Ensures scripts in .github/scripts/ can import lib/ regardless of sys.path[0]
ENV PYTHONPATH="/app"

# ---------------------------------------------------------------------------
# Dev — full repo code + tools for local development
# ---------------------------------------------------------------------------
FROM base AS dev

COPY . .

ENTRYPOINT ["/bin/bash"]
