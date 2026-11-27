# syntax=docker/dockerfile:1
# Amina Stays in one container, for the Africa's Talking Marketplace: the Next.js server listens on $PORT
# (8080) and proxies the API, Africa's Talking callbacks, admin, static files and media to Django (gunicorn on
# 127.0.0.1:8000); the scheduler runs alongside. docker/supervise.py starts, watches and stops all three.
#
#   docker build -t amina-stays .
#   docker run -p 8080:8080 -e DATABASE_URL=postgres://... -e SECRET_KEY=... -e ID_ENCRYPTION_KEY=... amina-stays
#
# marketplace/README.md has the variables and the registry push. docker-compose.yml keeps one container per
# process, from backend/Dockerfile and frontend/Dockerfile.

ARG PYTHON_IMAGE=python:3.14-slim-trixie
ARG NODE_IMAGE=node:24-trixie-slim
ARG BACKEND_PORT=8000

# ---------- Next.js standalone build ----------
# Debian rather than Alpine: the runtime is glibc, and so must be the native modules (sharp) traced into the build
FROM ${NODE_IMAGE} AS web-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# the rewrites to Django are resolved at build time: gunicorn's address inside this container
ARG BACKEND_PORT
ENV BACKEND_URL=http://127.0.0.1:${BACKEND_PORT} NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------- Django: dependencies and collected static files ----------
FROM ${PYTHON_IMAGE} AS api-build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# UV_PYTHON_DOWNLOADS=never: build the venv on this image's Python, the one the runtime stage has
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
ENV PATH="/app/backend/.venv/bin:$PATH"
# DEBUG=0 so the production storage writes its manifest of hashed, compressed files (without it a DEBUG=0 container
# answers the admin with a 500); the secret key only exists for this build step. Precompiled sources start faster.
RUN DEBUG=0 SECRET_KEY=collectstatic-build-step python manage.py collectstatic --noinput -v 0 \
 && python -m compileall -q apps config

# ---------- runtime ----------
FROM ${PYTHON_IMAGE}
ARG BACKEND_PORT
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/backend/.venv/bin:$PATH" \
    NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=8080 BACKEND_PORT=${BACKEND_PORT}
RUN groupadd --system --gid 10001 amina \
 && useradd --system --uid 10001 --gid amina --create-home --home-dir /home/amina --shell /usr/sbin/nologin amina
# Node for the Next.js server: the official glibc build, from the image the site was built with
COPY --from=web-build /usr/local/bin/node /usr/local/bin/node
COPY --from=api-build /app/backend /app/backend
# Next.js writes its cache (optimised images, revalidated pages) under .next at run time
COPY --from=web-build --chown=10001:10001 /src/frontend/.next/standalone /app/frontend
COPY --from=web-build --chown=10001:10001 /src/frontend/.next/static /app/frontend/.next/static
COPY --from=web-build --chown=10001:10001 /src/frontend/public /app/frontend/public
COPY docker/supervise.py /app/docker/supervise.py
# uploaded photos (MEDIA_ROOT) live on the container's disk: use photo URLs or mount a volume here
RUN install -d -o 10001 -g 10001 /app/backend/media
USER 10001:10001
WORKDIR /app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request as u; u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8080'), timeout=4)"]
ENTRYPOINT ["python", "/app/docker/supervise.py"]
