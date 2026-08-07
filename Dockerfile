# --- web build ---
FROM node:22-slim AS web
RUN corepack enable
WORKDIR /web
COPY apps/web/package.json apps/web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY apps/web/ ./
RUN pnpm build

# --- api ---
FROM python:3.12-slim
RUN pip install uv
WORKDIR /app/apps/api
COPY apps/api/pyproject.toml apps/api/uv.lock* ./
RUN uv sync --no-dev
COPY apps/api/ ./
COPY --from=web /web/dist /app/apps/web/dist
CMD ["uv", "run", "uvicorn", "lewis_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
