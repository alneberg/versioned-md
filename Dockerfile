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
RUN uv sync --frozen --compile-bytecode --all-extras --python 3.12 --python-preference only-managed
ENV PATH="/opt/venv/bin:$PATH"

# ---------------------------------------------------------------------------
# Dev — full repo code + tools for local development
# ---------------------------------------------------------------------------
FROM base AS dev

COPY . .

ENTRYPOINT ["/bin/bash"]

# ---------------------------------------------------------------------------
# Test — runs the test suite on Linux, like GitHub's ubuntu runners
#   docker build --target test -t versioned-md-test . && docker run --rm versioned-md-test
# ---------------------------------------------------------------------------
FROM base AS test

COPY . .
RUN uv pip install --python /opt/venv/bin/python --no-deps -e .
RUN git config --global user.name "Test Runner" && \
    git config --global user.email "test-runner@example.com" && \
    git config --global init.defaultBranch main

ENTRYPOINT ["python", "-m", "pytest"]
CMD ["-q"]
