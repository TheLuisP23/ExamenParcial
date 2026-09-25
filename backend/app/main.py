"""Punto de entrada de la app FastAPI (specs/04-api.md §4).

Monta los routers de `api/v1`, configura CORS y define el manejador de
errores genérico que traduce cualquier excepción no controlada al formato
único de error de specs/04-api.md §3, sin filtrar stack traces. También
resuelve el wiring de arranque de RF-07: si `daily_visits` está vacía, genera
y persiste el dataset sintético antes de aceptar tráfico.
"""

import json
import logging
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.v1.health import router as health_router
from app.api.v1.history import router as history_router
from app.api.v1.model import router as model_router
from app.api.v1.predictions import router as predictions_router
from app.api.v1.weather import router as weather_router
from app.clock import ayer_lima
from app.config import Settings, get_settings
from app.data.generator import generate
from app.data.repository import VisitsRepository
from app.domain.config_loader import load_model_config
from app.domain.holidays import load_holiday_calendar

logger = logging.getLogger("cueva.api")
access_logger = logging.getLogger("cueva.access")

settings = get_settings()


# --------------------------------------------------------------------------
# RNF-10: logs en JSON a stdout con `nivel`, `ruta`, `status`, `duracion_ms`,
# `version`. RNF-05/P5: la llave de WeatherAPI nunca debe aparecer en un log,
# pase lo que pase -- ver `RedactWeatherApiKeyFilter` más abajo.
# --------------------------------------------------------------------------

# Atributos "de fábrica" de `logging.LogRecord` (ver la documentación de
# `logging`): cualquier otro atributo del record viene de un `extra={...}`
# explícito (p. ej. `ruta`/`status`/`duracion_ms`/`version`) y es candidato a
# redacción si resulta ser un string que contiene la llave.
_STANDARD_LOGRECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
    }
)


class RedactWeatherApiKeyFilter(logging.Filter):
    """RNF-05/P5 ("Secretos fuera del repo"): última línea de defensa contra
    fugas de `WEATHERAPI_KEY` en logs. `app.clients.weatherapi` (BE-05) ya
    evita construir mensajes con la URL completa, pero este filtro es una
    capa global e independiente de esa disciplina manual: inspecciona el
    mensaje ya formateado (`record.getMessage()`) y cualquier campo `extra`
    de tipo string de **todo** `LogRecord` que llegue al handler raíz
    (incluidos los de `uvicorn`/`httpx`/`httpcore` si algún día subieran de
    nivel por error humano) y reemplaza el valor literal de la llave por
    `"***REDACTED***"` si aparece. Guarda: no hace nada si no hay llave
    configurada (evita un `IndexError`/bucle vacío con string vacío)."""

    def __init__(self, secret: str | None) -> None:
        super().__init__()
        self._secret = secret or None

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secret:
            return True
        try:
            mensaje = record.getMessage()
        except Exception:  # noqa: BLE001 - un filtro nunca debe tumbar el logging
            return True
        if self._secret in mensaje:
            record.msg = mensaje.replace(self._secret, "***REDACTED***")
            record.args = None
        for clave, valor in list(record.__dict__.items()):
            if clave in _STANDARD_LOGRECORD_ATTRS:
                continue
            if isinstance(valor, str) and self._secret in valor:
                setattr(record, clave, valor.replace(self._secret, "***REDACTED***"))
        return True


class JsonFormatter(logging.Formatter):
    """RNF-10: serializa cada `LogRecord` como una línea JSON a stdout con
    `nivel`, `mensaje`, `logger`, `timestamp` siempre, y `ruta`/`status`/
    `duracion_ms`/`version` cuando el logger los pasó vía `extra={...}`
    (los emite el middleware de acceso de más abajo en cada request).

    También aplica, como red de seguridad adicional a
    `RedactWeatherApiKeyFilter`, una redacción final sobre la línea JSON ya
    serializada completa (incluye por tanto tracebacks de `exc_info`): si
    por cualquier vía no contemplada la llave llegara a colarse en el
    record, no sale de este formatter hacia stdout.
    """

    _EXTRA_FIELDS = ("ruta", "status", "duracion_ms", "version")

    def __init__(self, secret: str | None = None) -> None:
        super().__init__()
        self._secret = secret or None

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "mensaje": record.getMessage(),
        }
        for campo in self._EXTRA_FIELDS:
            if hasattr(record, campo):
                payload[campo] = getattr(record, campo)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        linea = json.dumps(payload, ensure_ascii=False, default=str)
        if self._secret and self._secret in linea:
            linea = linea.replace(self._secret, "***REDACTED***")
        return linea


def _configure_logging(settings: Settings) -> None:
    """Reemplaza el `logging.basicConfig(level=...)` simple de BE-01 por un
    handler explícito a stdout con `JsonFormatter` (RNF-10) y
    `RedactWeatherApiKeyFilter` (RNF-05/P5), instalados en el logger raíz
    para que apliquen a todos los loggers de la app y de sus dependencias
    (`uvicorn`, `httpx`, etc.). Limpia los handlers/filtros previos del
    logger raíz para no duplicar salidas si esta función llegara a
    invocarse más de una vez en el mismo proceso.

    El filtro de redacción se instala dos veces a propósito: en el logger
    raíz (`root.addFilter`) para que la redacción del record ocurra *antes*
    de que `Logger.callHandlers` lo reparta a cualquier handler -- el propio
    y cualquier otro que se añada después (p. ej. el handler que instala
    `caplog` de pytest para IT-13/QA-03, registrado en tiempo de test,
    después de este arranque) -- sin depender del orden de registro de los
    handlers; y en el handler propio (`handler.addFilter`, tal como pide la
    tarea) como segunda capa por si algún día se toca el filtro del logger
    raíz sin tocar este módulo."""
    root = logging.getLogger()
    root.handlers.clear()
    root.filters.clear()
    redact_filter = RedactWeatherApiKeyFilter(settings.weatherapi_key)
    root.addFilter(redact_filter)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter(secret=settings.weatherapi_key))
    handler.addFilter(redact_filter)
    root.addHandler(handler)
    root.setLevel(settings.log_level)


_configure_logging(settings)


def generar_dataset_inicial_si_vacio(database_path: str | None = None) -> None:
    """RF-07: si la tabla `daily_visits` está vacía, genera y persiste el
    dataset sintético (specs/02-decision-datos.md §4) con los parámetros de
    calibración de `config/model.yaml → calibracion`. Idempotente: no hace
    nada si ya hay datos. `generate()` en sí es pura -- `end_date` se inyecta
    aquí como "ayer" en America/Lima (`app.clock.ayer_lima`), nunca se lee el
    reloj dentro del generador.
    """
    repo = VisitsRepository(database_path or settings.database_path)
    if not repo.is_empty():
        return

    calib = load_model_config()["calibracion"]
    holidays = load_holiday_calendar()
    resultado = generate(
        seed=int(calib["semilla"]),
        years=int(calib["anios"]),
        end_date=ayer_lima(),
        holidays=holidays,
    )
    repo.save_generated(resultado, seed=int(calib["semilla"]))
    logger.info(
        "Dataset sintético inicial generado: %d filas, base_diaria=%.4f",
        len(resultado.rows),
        resultado.base_diaria,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    generar_dataset_inicial_si_vacio()
    yield


app = FastAPI(
    title="Cueva de las Lechuzas · API de predicción de visitantes",
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS: en producción, Nginx sirve frontend y API bajo el mismo origen
# (specs/04-api.md §4), por lo que no se necesitan orígenes cruzados. En
# desarrollo local el frontend (Vite, http://localhost:5173) sí es un origen
# distinto del backend (http://localhost:8000), así que se habilitan solo
# los orígenes típicos de desarrollo local para no bloquear `npm run dev`.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """RNF-10: un log de acceso estructurado por cada request, con `ruta`
    (``request.url.path``, sin query string, para no arrastrar accidentalmente
    parámetros sensibles), `status`, `duracion_ms` y `version`. Es un log de
    acceso HTTP general e independiente de los logs de negocio de cada router
    (p. ej. `cueva.weatherapi`): se emite igual para rutas que no llaman a
    WeatherAPI, como `/health`."""
    inicio = time.perf_counter()
    response = await call_next(request)
    duracion_ms = (time.perf_counter() - inicio) * 1000
    nivel = logging.INFO if response.status_code < 500 else logging.ERROR
    access_logger.log(
        nivel,
        "%s %s -> %d",
        request.method,
        request.url.path,
        response.status_code,
        extra={
            "ruta": request.url.path,
            "status": response.status_code,
            "duracion_ms": round(duracion_ms, 2),
            "version": settings.app_version,
        },
    )
    return response


app.include_router(health_router, prefix="/api/v1")
app.include_router(predictions_router, prefix="/api/v1")
app.include_router(weather_router, prefix="/api/v1")
app.include_router(history_router, prefix="/api/v1")
app.include_router(model_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Traduce cualquier excepción no controlada a `ERROR_INTERNO` (specs/04-api.md §3).

    No se expone el detalle de la excepción en la respuesta; solo se registra
    en el log del servidor.
    """
    logger.exception("Excepción no controlada en %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "codigo": "ERROR_INTERNO",
                "mensaje": "Ocurrió un error interno. Intenta nuevamente más tarde.",
            }
        },
    )
