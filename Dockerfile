# FastOMOP Dockerfile

FROM python:3.13-slim AS builder

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install UV package manager
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies using UV with increased timeout
ENV UV_HTTP_TIMEOUT=300
RUN uv sync --frozen --no-dev

# Final stage - minimal runtime image
FROM python:3.13-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 fastomop && \
    mkdir -p /app /app/data && \
    chown -R fastomop:fastomop /app

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY --chown=fastomop:fastomop . .

# Switch to non-root user
USER fastomop

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Expose web interface port
EXPOSE 7777

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:7777/health || exit 1

# Default command - run web interface
CMD ["python", "-m", "agno_fastomop.web_interface"]
