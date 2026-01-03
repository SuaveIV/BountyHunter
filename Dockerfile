FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy dependency definitions
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev deps, no project root yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy project files
COPY . .

# Install the project itself
RUN uv sync --frozen --no-dev

# Create a directory for the database
RUN mkdir -p data

# Use the virtual environment's python
CMD ["/app/.venv/bin/python", "src/bounty_discord/run.py"]
