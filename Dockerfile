FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install the package in editable mode with all dependencies
RUN uv sync --frozen --no-dev

# Install Playwright browsers
RUN uv run playwright install chromium --with-deps

# Copy source code
COPY src/ src/
COPY .env.example .env

# Ensure venv bin is in PATH
ENV PATH="/app/.venv/bin:$PATH"

# Default command
CMD ["brone-tugas", "bot"]