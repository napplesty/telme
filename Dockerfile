# syntax=docker/dockerfile:1

# ============================================================
# Stage 1: Builder - install dependencies
# ============================================================
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies (needed for pynacl/cffi)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy project files needed for install
COPY pyproject.toml ./
COPY server/ ./server/
COPY client/ ./client/

# Install the package and all its dependencies into a virtual env
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir .

# ============================================================
# Stage 2: Runtime - minimal image
# ============================================================
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="Telme Server" \
      org.opencontainers.image.description="End-to-end encrypted chat server" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.source="https://github.com/telme-chat/telme" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Install runtime dependency for libsodium + curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libsodium23 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual env from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Create non-root user
RUN groupadd -r telme && useradd -r -g telme -d /app -s /sbin/nologin telme

WORKDIR /app

# Copy server source (needed at runtime for the app factory)
COPY --chown=telme:telme server/ ./server/
COPY --chown=telme:telme client/ ./client/

USER telme

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["uvicorn", "server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
