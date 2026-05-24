FROM python:3.12-slim

WORKDIR /srv/logto-bridge

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_COMPILE=1

# Copy requirements.txt for caching dependencies
COPY requirements.txt /tmp/requirements.txt

# Install packages, create non-root user, and clean up apt lists
RUN set -eux; \
    pip install --no-cache-dir -r /tmp/requirements.txt; \
    rm -f /tmp/requirements.txt; \
    groupadd --gid "${APP_GID}" appgroup; \
    useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin appuser; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/* /tmp/* /root/.cache; \
    pip cache purge 2>/dev/null || true

# Copy sources
COPY --chown=appuser:appgroup app/ ./app/

# Clean up pycaches
RUN find ./app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port 8000 --log-level $(printf '%s' \"${LOG_LEVEL:-info}\" | tr '[:upper:]' '[:lower:]')"]
