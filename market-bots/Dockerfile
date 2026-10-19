# Pure-stdlib Python: no pip install, no compiler, multi-arch (amd64 PC / arm64 Oracle VPS) from the same file.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MB_CONFIG=/app/profiles.toml \
    MB_STATE_DIR=/data \
    MB_SEND=off

RUN useradd --system --uid 10001 --home-dir /app bots && mkdir -p /data && chown bots /data
WORKDIR /app
COPY market_bots ./market_bots
COPY profiles.toml ./profiles.toml

USER bots
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-m", "market_bots", "healthcheck"]
CMD ["python", "-m", "market_bots", "run"]
