# syntax=docker/dockerfile:1
#
# Build context = RAÍZ del repo (no backend/), para poder copiar config/*.yaml
# (P7: coeficientes fuera del código) dentro de la imagen. Ver docker-compose.yml
# y .github/workflows/{ci,deploy}.yml: build.context=., dockerfile=backend/Dockerfile.

# --- Etapa 1: build (instala dependencias en un venv) ---------------------
FROM python:3.12-slim AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/pyproject.toml ./
COPY backend/app ./app

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# --- Etapa 2: runtime (imagen final, sin herramientas de build) -----------
FROM python:3.12-slim AS final

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Usuario no root (RNF-06)
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY backend/app ./app
COPY config ./config

# /data es donde monta el volumen cueva-data (SQLite, DATABASE_PATH=/data/cueva.db).
# Se crea y se da dueño aquí para que el volumen nombrado herede el permiso al
# inicializarse; si no, Docker lo crea como root y el proceso no-root no puede escribir.
RUN mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
