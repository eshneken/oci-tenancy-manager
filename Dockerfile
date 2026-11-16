# One immutable installed application plus public UI; API/worker/maintenance select existing commands.
FROM ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 AS uv
FROM node:24-trixie-slim@sha256:af02d57b57719b9657a45199a79264a9437940cd55b3c7b3fc99615654f124a0 AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts frontend/generate-contracts.mjs ./
COPY frontend/src ./src
COPY frontend/public ./public
COPY backend/contracts /build/backend/contracts
RUN npm run contracts:check && npm run build

FROM python:3.12-alpine3.24@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89 AS backend
COPY --from=uv /uv /usr/local/bin/uv
# Install into the same absolute venv path used at runtime; use the base interpreter, never a download.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /build/backend
COPY backend/pyproject.toml backend/uv.lock backend/alembic.ini ./
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/config/application.toml ./config/application.toml
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-alpine3.24@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89 AS runtime
# Refresh supported-distribution packages; no compilers or hand-built system libraries enter runtime.
RUN apk upgrade --no-cache && apk add --no-cache ca-certificates openssl \
    && addgroup -g 10001 otm && adduser -D -H -u 10001 -G otm -s /sbin/nologin otm
# Use installed tools, suppress bytecode writes, flush logs and locate immutable built frontend assets.
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OTM_FRONTEND_DIST=/opt/otm/public
WORKDIR /opt/otm
COPY --from=backend /opt/venv /opt/venv
COPY --from=frontend /build/frontend/dist ./public
USER 10001:10001
EXPOSE 8080
# Explicit laptop composition fails closed without operator-provided settings and credentials.
# Hosted composition is a later deployment slice, not an implicit local-provider fallback.
CMD ["uvicorn", "otm.local_server:create_local_application", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
