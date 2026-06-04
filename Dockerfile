FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync

# Install Playwright browsers (THIS IS THE FIX)
RUN uv run playwright install chromium --with-deps

# Copy source code
COPY . .

# Default command
CMD ["brone-tugas", "bot"]