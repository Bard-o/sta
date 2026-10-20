FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# El entorno virtual vive fuera de /app para que el volumen del código no lo tape.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project \
    && useradd --uid 1000 --create-home app \
    && chown -R app:app /opt/venv /tmp/uv-cache

# Mismo uid que el usuario típico de Linux/WSL2: lo que se genere en el volumen
# (migraciones, uv.lock) queda a tu nombre y no de root.
USER app

COPY --chown=app:app . .

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
