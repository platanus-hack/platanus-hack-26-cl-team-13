# Orquestador de AIgis para Render (o cualquier host de contenedores).
# Contexto de build: raíz del repo, porque necesita tasks/ y sandbox/.
#   docker build -f services/api/Dockerfile -t aigis-api .
# En Render las cajas corren en E2B: Render no admite Docker dentro del contenedor.
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /usr/local/bin/uv

# git: el orquestador no lo usa aquí, pero los scripts de tareas sí lo esperan disponible
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/services/api
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services/api/aigis ./aigis
COPY tasks /app/tasks
COPY sandbox /app/sandbox

ENV PATH="/app/services/api/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    AIGIS_SANDBOX_PROVIDER=e2b \
    AIGIS_DEV=false

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn aigis.app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
