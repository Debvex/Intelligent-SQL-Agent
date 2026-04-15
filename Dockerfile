# --- Builder stage ---
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Final stage ---
FROM python:3.11-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Ensure scripts are executable
RUN chmod +x scripts/*.sh

# Switch to non-root user
USER appuser

EXPOSE 8000

ENTRYPOINT ["bash", "scripts/app-entrypoint.sh"]