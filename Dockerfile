# ===== Stage 1: build the React SPA =====
FROM node:18-alpine AS webbuild
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./apps/web/
RUN cd apps/web && npm ci --silent --no-audit --no-fund
COPY apps/web ./apps/web
RUN cd apps/web && npm run build

# ===== Stage 2: Python runtime =====
FROM python:3.11-slim AS runtime
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY apps/api/requirements.txt ./apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt gunicorn

# App
COPY apps/api ./apps/api
COPY infra ./infra

# Built SPA from stage 1
COPY --from=webbuild /app/apps/web/dist ./apps/web/dist

ENV PORT=8080
ENV BQ_PROJECT=""
ENV BQ_DATASET="ge_observability"

EXPOSE 8080

# Use gunicorn for prod (uvicorn workers under gunicorn for stability)
CMD exec gunicorn -w 2 -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT} \
    --chdir apps/api \
    --access-logfile - \
    --error-logfile - \
    main:app
