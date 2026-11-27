FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
# DEBUG=0 so the production storage writes its manifest of hashed, compressed files (without it a DEBUG=0 container
# answers the admin with a 500); the secret key only exists for this build step
RUN DEBUG=0 SECRET_KEY=collectstatic-build-step python manage.py collectstatic --noinput -v 0
EXPOSE 8000
# --keep-alive 0: answer each proxied request on its own connection, so the Next.js proxy never reuses one
# gunicorn is closing at that moment (which surfaces as an intermittent "socket hang up" 500)
CMD ["gunicorn", "config.wsgi", "-b", "0.0.0.0:8000", "-w", "3", "--threads", "4", "--keep-alive", "0", "--access-logfile", "-"]
