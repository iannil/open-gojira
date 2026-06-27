# ── Stage 1: Build ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies for psycopg2 (libpq-dev) and other C extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies into a virtual environment
COPY requirements.txt .
RUN python -m venv /build/venv && \
    /build/venv/bin/pip install --no-cache-dir --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn && \
    /build/venv/bin/pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

# ── Stage 2: Runtime ───────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="Gojira Team"
LABEL description="Gojira Investment System - Backend API"

# Create non-root user
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /build/venv /app/.venv

# Fix shebangs: builder stage path ( /build/venv ) → runtime path ( /app/.venv )
# Without this, scripts like uvicorn fail with "no such file or directory"
RUN sed -i 's|#!/build/venv/bin/python|#!/app/.venv/bin/python|g' /app/.venv/bin/*

# Copy application code
COPY . .

# Ensure data and logs directories exist for observability logs
RUN mkdir -p /app/data /app/logs/observability && chown -R appuser:appuser /app/data /app/logs

# Use the virtual environment binaries
ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3001/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3001", "--workers", "2"]
