# API container. Build context MUST be the repo root (it needs packages/core).
#   docker build -f apps/api/Dockerfile -t prop-search-api .
FROM python:3.12-slim

WORKDIR /app

# Install the shared core first, then the API (its prop-search-core dep is then satisfied).
COPY packages/core ./packages/core
RUN pip install --no-cache-dir ./packages/core

COPY apps/api ./apps/api
RUN pip install --no-cache-dir ./apps/api

# Hosts inject PORT; default 8000 for local runs.
ENV PORT=8000
EXPOSE 8000
# --no-access-log: our middleware logs one line per request (with latency) — avoid dupes.
CMD ["sh", "-c", "uvicorn prop_search_api.main:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
