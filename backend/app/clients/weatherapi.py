"""Cliente HTTP para WeatherAPI.com (specs/05-integracion-weatherapi.md, BE-05).

Cubre RF-01 (mostrar el clima) y RF-06 (degradar sin romper `/predicciones`
cuando WeatherAPI no está disponible). Capa de infraestructura: hace las
únicas dos llamadas HTTP salientes de la aplicación (`forecast.json`,
`current.json`), con caché en SQLite (tabla `weather_cache`, ya creada por
`app.data.repository.VisitsRepository.create_schema()`), timeout, reintentos
y degradación según specs/05 §4-§5.

`app/domain/` **no** importa este módulo (regla de arquitectura de
specs/04-api.md §4); este módulo tampoco importa `app/domain/` a propósito,
para no acoplar el cliente HTTP al modelo de predicción -- expone sus
propias estructuras (`DayForecast`, `HourlyForecastPoint`, `ForecastResult`,
`CurrentWeather`) y deja que BE-06 (routers) las traduzca a
`app.domain.factors.ClimaInput`/`HourlyPoint` y al esquema de
`GET /predicciones` / `GET /clima/actual`.

Interfaz pública (contrato para BE-06 y QA-03):

- ``WeatherApiClient(settings)`` -- ``settings`` es opcional; por defecto
  usa ``Depends(get_settings)`` (la clase se puede usar directamente como
  ``Depends(WeatherApiClient)`` en un router FastAPI) o, fuera de FastAPI,
  ``WeatherApiClient(get_settings())``.
- ``await client.get_forecast(days=3) -> ForecastResult`` -- pronóstico de
  ``days`` días (hoy incluido) para las coordenadas de
  ``config/location.yaml``. Usado por ``/predicciones``.
- ``await client.get_current() -> CurrentWeather`` -- clima actual. Usado
  por ``/clima/actual``.
- Ambos métodos **nunca** devuelven ``None`` ni dejan escapar excepciones de
  ``httpx``: en éxito devuelven su dataclass (con ``source in {"api",
  "cache"}`` para que el router sepa si el dato es fresco o degradado);
  cuando no hay datos utilizables (ni respuesta fresca de la API ni caché de
  hasta 6 horas) levantan ``WeatherUnavailableError`` -- la única excepción
  que el router necesita capturar para implementar RF-06
  (``/predicciones``: seguir con ``clima=None`` => ``f_clima=1.0``) o el 503
  ``CLIMA_NO_DISPONIBLE`` de ``/clima/actual`` (specs/04-api.md §3).

Seguridad (P5 de specs/00-constitucion.md): la llave y la URL completa
(que la contiene como query param) nunca se registran ni se devuelven. Los
logs de este módulo sólo incluyen ``endpoint`` (``"forecast"``/``"current"``),
``status`` (código HTTP, ``"timeout"`` o ``"error"``) y ``duracion_ms``, como
mensajes con forma de JSON emitidos vía el logger estándar de `logging`
(``cueva.weatherapi``). El formateo del *registro* completo como JSON a
stdout (con ``nivel``/``ruta``/``version``, RNF-10) es responsabilidad de
BE-07 ("Logs JSON y ocultamiento de la llave", que depende de esta tarea);
aquí sólo se garantiza que el contenido de cada mensaje ya es JSON y jamás
incluye la llave ni la URL completa. Como medida defensiva adicional, este
módulo baja el nivel de los loggers internos de ``httpx``/``httpcore`` a
``WARNING`` al importarse, para que un `LOG_LEVEL=DEBUG` en la app no
termine imprimiendo las URLs completas (con la llave) que esas librerías
registran en sus propios logs de depuración.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import Depends

from app.config import Settings, get_settings

logger = logging.getLogger("cueva.weatherapi")

# Defensa en profundidad: los logs de depuración de httpx/httpcore incluyen
# la URL completa de la petición (con la llave como query param). Bajar su
# nivel evita que un LOG_LEVEL=DEBUG de la app los deje pasar (P5, RNF-05).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

_BASE_URL = "https://api.weatherapi.com/v1"
_TIMEOUT_SECONDS = 5.0
_BACKOFFS_SECONDS = [0.5, 1.0]  # specs/05 §4: 2 reintentos, 0.5s y luego 1s
_MAX_ATTEMPTS = 1 + len(_BACKOFFS_SECONDS)
_STALE_CACHE_MAX_AGE = timedelta(hours=6)  # specs/05 §4: caché "de hasta 6 horas"
_WEATHERAPI_INTERNAL_ERROR_CODE = 9999  # specs/05 §5: única excepción 4xx-que-sí-reintenta


class WeatherUnavailableError(Exception):
    """No hay dato de clima utilizable: ni respuesta fresca de la API ni
    caché de hasta 6 horas (specs/05 §4). El router (BE-06) la captura para
    degradar (RF-06: `/predicciones` sigue con `clima=None`/`f_clima=1.0`) o
    para responder 503 `CLIMA_NO_DISPONIBLE` en `/clima/actual`
    (specs/04-api.md §3) -- esa decisión de status HTTP es del router, no de
    este cliente.
    """

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        super().__init__(f"Clima no disponible ({endpoint}): sin API y sin caché válida")


class _FetchFailed(Exception):
    """Error interno de `_fetch`: la llamada HTTP (tras agotar reintentos si
    aplicaba) no produjo un JSON utilizable. Nunca se deja escapar fuera de
    este módulo ni se le adjunta la excepción original de httpx (`raise ...
    from None`) para no arrastrar accidentalmente el request/URL con la
    llave hacia un traceback logueado más arriba (p. ej. el
    `unhandled_exception_handler` de `app.main`, que sí usa
    `logger.exception`)."""


# --------------------------------------------------------------------------
# Estructuras de datos expuestas (documentadas en el docstring del módulo).
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HourlyForecastPoint:
    """Un punto horario de `forecastday[].hour[]`."""

    hour: int  # 0-23, hora local (America/Lima, tal como la da WeatherAPI)
    time: str  # `hour[].time` crudo, "YYYY-MM-DD HH:MM"
    chance_of_rain: int  # `hour[].chance_of_rain`, 0-100
    condition_code: int | None  # `hour[].condition.code`


@dataclass(frozen=True)
class DayForecast:
    """Un día de `forecast.forecastday[]` (specs/05 §3)."""

    date: date  # `forecastday[].date`
    totalprecip_mm: float  # `day.totalprecip_mm`
    daily_chance_of_rain: int  # `day.daily_chance_of_rain`
    maxtemp_c: float  # `day.maxtemp_c`
    mintemp_c: float  # `day.mintemp_c`
    condition_text: str  # `day.condition.text`
    condition_code: int  # `day.condition.code`
    condition_icon: str  # `day.condition.icon`, con `https:` antepuesto
    hourly: list[HourlyForecastPoint]  # `hour[]`, las 24 horas (el consumidor filtra 08-17)


@dataclass(frozen=True)
class ForecastResult:
    """Resultado de `get_forecast()`."""

    days: list[DayForecast]
    alert_headlines: list[str]  # `alerts.alert[].headline`, para `ALERTA_OFICIAL`
    source: str  # "api" (fresco) o "cache" (TTL vigente o degradado hasta 6h)


@dataclass(frozen=True)
class CurrentWeather:
    """Resultado de `get_current()` (`current.json`, para `ClimaActual`)."""

    temp_c: float
    feelslike_c: float
    condition_text: str
    condition_code: int
    condition_icon: str  # con `https:` antepuesto
    humidity: int
    precip_mm: float
    last_updated: str  # `current.last_updated` crudo, "YYYY-MM-DD HH:MM" hora Lima
    source: str  # "api" o "cache"


# --------------------------------------------------------------------------
# Coordenadas (config/location.yaml, P7: configuración, no constantes).
# --------------------------------------------------------------------------


def _find_config_dir() -> Path:
    override = os.environ.get("CONFIG_DIR")
    if override:
        candidate = Path(override)
        if (candidate / "location.yaml").is_file():
            return candidate

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config"
        if (candidate / "location.yaml").is_file():
            return candidate

    raise FileNotFoundError(
        "No se encontro config/location.yaml. Defina CONFIG_DIR o ejecute "
        "desde un checkout completo del repositorio (config/ hermano de backend/)."
    )


def _load_coordinates() -> tuple[float, float]:
    """`lat`, `lon` de `config/location.yaml` (specs/05 §2: nunca hardcodeadas)."""
    path = _find_config_dir() / "location.yaml"
    with path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return float(cfg["lat"]), float(cfg["lon"])


# --------------------------------------------------------------------------
# Caché SQLite (tabla `weather_cache`, esquema de app.data.repository).
# --------------------------------------------------------------------------

# Mismo esquema que `app.data.repository._SCHEMA` para `weather_cache`. Se
# repite aquí (en vez de importar `app.data.repository`) porque BE-05 no
# debe modificar ese módulo y porque este cliente no depende de
# `VisitsRepository`: en producción la tabla ya existe (la crea el arranque
# de `app.main` vía `VisitsRepository.create_schema()`), pero este
# `CREATE TABLE IF NOT EXISTS` idéntico hace que el cliente también funcione
# de forma autónoma (p. ej. en los tests de este archivo).
_WEATHER_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS weather_cache (
    cache_key   TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    fetched_at  TEXT NOT NULL
);
"""


class _WeatherCache:
    """Acceso a la tabla `weather_cache`. Todas las consultas son
    parametrizadas (P5)."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._database_path)
        try:
            conn.execute(_WEATHER_CACHE_SCHEMA)
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get(self, cache_key: str, *, max_age: timedelta) -> dict[str, Any] | None:
        """Payload cacheado si existe y su antigüedad es `<= max_age`."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, fetched_at FROM weather_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        payload_raw, fetched_at_raw = row
        fetched_at = datetime.fromisoformat(fetched_at_raw)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        if datetime.now(UTC) - fetched_at > max_age:
            return None
        return json.loads(payload_raw)

    def set(self, cache_key: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO weather_cache (cache_key, payload, fetched_at) "
                "VALUES (?, ?, ?)",
                (cache_key, json.dumps(payload), datetime.now(UTC).isoformat()),
            )


# --------------------------------------------------------------------------
# Logging estructurado (nunca URL completa ni la llave -- ver docstring).
# --------------------------------------------------------------------------


def _log(nivel: str, **campos: Any) -> None:
    mensaje = json.dumps(campos, ensure_ascii=False, default=str)
    if nivel == "ERROR":
        logger.error(mensaje)
    elif nivel == "WARNING":
        logger.warning(mensaje)
    else:
        logger.info(mensaje)


# --------------------------------------------------------------------------
# Mapeo de errores documentados de WeatherAPI (specs/05 §5).
# --------------------------------------------------------------------------


def _weatherapi_error_code(response: httpx.Response) -> int | None:
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        codigo = error.get("code")
        if isinstance(codigo, int):
            return codigo
    return None


def _es_reintentable(status_code: int, codigo_weatherapi: int | None) -> bool:
    """specs/05 §4-§5: timeout/5xx siempre; 4xx nunca, **excepto** el 400
    con `error.code == 9999` (error interno de WeatherAPI)."""
    if status_code >= 500:
        return True
    return status_code == 400 and codigo_weatherapi == _WEATHERAPI_INTERNAL_ERROR_CODE


# --------------------------------------------------------------------------
# Parseo de las respuestas crudas de WeatherAPI a las estructuras públicas.
# --------------------------------------------------------------------------


def _https_icon(icon: str) -> str:
    """specs/05 §3: `icono_url` antepone `https:` si falta (WeatherAPI
    devuelve URLs protocol-relative, `//cdn.weatherapi.com/...`)."""
    if not icon:
        return icon
    if icon.startswith("http://") or icon.startswith("https://"):
        return icon
    if icon.startswith("//"):
        return f"https:{icon}"
    return f"https://{icon}"


def _parse_hour(hour_raw: dict[str, Any]) -> HourlyForecastPoint:
    time_str = str(hour_raw["time"])
    hour = int(time_str.split(" ")[1].split(":")[0])
    condition = hour_raw.get("condition") or {}
    return HourlyForecastPoint(
        hour=hour,
        time=time_str,
        chance_of_rain=int(hour_raw.get("chance_of_rain", 0)),
        condition_code=condition.get("code"),
    )


def _parse_day(day_raw: dict[str, Any]) -> DayForecast:
    day = day_raw["day"]
    condition = day.get("condition") or {}
    return DayForecast(
        date=date.fromisoformat(day_raw["date"]),
        totalprecip_mm=float(day["totalprecip_mm"]),
        daily_chance_of_rain=int(day.get("daily_chance_of_rain", 0)),
        maxtemp_c=float(day["maxtemp_c"]),
        mintemp_c=float(day["mintemp_c"]),
        condition_text=str(condition.get("text", "")),
        condition_code=int(condition.get("code", 0)),
        condition_icon=_https_icon(str(condition.get("icon", ""))),
        hourly=[_parse_hour(h) for h in day_raw.get("hour", [])],
    )


def _parse_forecast(payload: dict[str, Any], *, source: str) -> ForecastResult:
    forecastday = payload.get("forecast", {}).get("forecastday", [])
    alerts_raw = (payload.get("alerts") or {}).get("alert") or []
    headlines = [str(a["headline"]) for a in alerts_raw if a.get("headline")]
    return ForecastResult(
        days=[_parse_day(d) for d in forecastday],
        alert_headlines=headlines,
        source=source,
    )


def _parse_current(payload: dict[str, Any], *, source: str) -> CurrentWeather:
    current = payload["current"]
    condition = current.get("condition") or {}
    return CurrentWeather(
        temp_c=float(current["temp_c"]),
        feelslike_c=float(current.get("feelslike_c", current["temp_c"])),
        condition_text=str(condition.get("text", "")),
        condition_code=int(condition.get("code", 0)),
        condition_icon=_https_icon(str(condition.get("icon", ""))),
        humidity=int(current.get("humidity", 0)),
        precip_mm=float(current.get("precip_mm", 0.0)),
        last_updated=str(current.get("last_updated", "")),
        source=source,
    )


# --------------------------------------------------------------------------
# Cliente.
# --------------------------------------------------------------------------


class WeatherApiClient:
    """Cliente de WeatherAPI.com con caché, timeout y reintentos (specs/05).

    Ver el docstring del módulo para el contrato completo. Los dos métodos
    públicos son `async` (usan `httpx.AsyncClient`): los reintentos usan
    `asyncio.sleep`, que no bloquea el event loop de FastAPI mientras espera
    el backoff -- importante porque, en el peor caso (timeout en los 3
    intentos), una sola llamada puede tardar ~3 x 5s + 0.5s + 1s = 16.5s.
    """

    def __init__(self, settings: Settings = Depends(get_settings)) -> None:
        self._settings = settings
        self._lat, self._lon = _load_coordinates()
        self._q = f"{self._lat},{self._lon}"
        self._cache = _WeatherCache(settings.database_path)

    def _forecast_cache_key(self, days: int) -> str:
        return f"forecast:{self._q}:{days}"

    def _current_cache_key(self) -> str:
        return f"current:{self._q}"

    async def get_forecast(self, *, days: int = 3) -> ForecastResult:
        """RF-01/RF-05: pronóstico de `days` días para las coordenadas de
        `config/location.yaml`. Lee caché fresca primero (RNF-08: evita
        llamadas repetidas); si no hay, llama a la API; si la API falla,
        usa caché de hasta 6h con un warning (specs/05 §4); si nada de eso
        funciona, levanta `WeatherUnavailableError("forecast")` (RF-06: el
        router sigue con `clima=None` => `f_clima=1.0`, nunca rompe
        `/predicciones`)."""
        cache_key = self._forecast_cache_key(days)
        return await self._get(
            endpoint="forecast",
            params={"days": days, "aqi": "no", "alerts": "yes", "lang": "es"},
            cache_key=cache_key,
            parse=lambda payload, source: _parse_forecast(payload, source=source),
        )

    async def get_current(self) -> CurrentWeather:
        """RF-01: clima actual para `/clima/actual`. Mismo contrato de
        caché/degradación que `get_forecast`; en fallo total levanta
        `WeatherUnavailableError("current")` -- el router decide si eso es
        un 503 `CLIMA_NO_DISPONIBLE` (specs/04-api.md §3)."""
        cache_key = self._current_cache_key()
        return await self._get(
            endpoint="current",
            params={"aqi": "no", "lang": "es"},
            cache_key=cache_key,
            parse=lambda payload, source: _parse_current(payload, source=source),
        )

    async def _get(
        self,
        *,
        endpoint: str,
        params: dict[str, Any],
        cache_key: str,
        parse: Any,
    ) -> Any:
        ttl = timedelta(seconds=self._settings.weather_cache_ttl_seconds)
        fresh = self._cache.get(cache_key, max_age=ttl)
        if fresh is not None:
            return parse(fresh, "cache")

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                payload = await self._fetch(endpoint, params, client=client)
        except _FetchFailed:
            stale = self._cache.get(cache_key, max_age=_STALE_CACHE_MAX_AGE)
            if stale is not None:
                _log("WARNING", evento="weather_cache_fallback", endpoint=endpoint)
                return parse(stale, "cache")
            _log("ERROR", evento="clima_no_disponible", endpoint=endpoint)
            raise WeatherUnavailableError(endpoint) from None

        self._cache.set(cache_key, payload)
        return parse(payload, "api")

    async def _fetch(
        self, endpoint: str, params: dict[str, Any], *, client: httpx.AsyncClient
    ) -> dict[str, Any]:
        """Hace `GET {endpoint}.json` con hasta `_MAX_ATTEMPTS` intentos
        (specs/05 §4). Devuelve el JSON en éxito; levanta `_FetchFailed` si
        se agotan los intentos o ante un error no reintentable."""
        url = f"{_BASE_URL}/{endpoint}.json"
        full_params = {**params, "key": self._settings.weatherapi_key, "q": self._q}

        for intento in range(_MAX_ATTEMPTS):
            inicio = time.monotonic()
            try:
                response = await client.get(url, params=full_params)
            except httpx.TimeoutException:
                duracion_ms = int((time.monotonic() - inicio) * 1000)
                _log("WARNING", endpoint=endpoint, status="timeout", duracion_ms=duracion_ms)
                if intento < _MAX_ATTEMPTS - 1:
                    await asyncio.sleep(_BACKOFFS_SECONDS[intento])
                    continue
                _log("ERROR", endpoint=endpoint, evento="reintentos_agotados", status="timeout")
                raise _FetchFailed("timeout") from None
            except httpx.RequestError:
                # Errores de red/conexión (no HTTP): no están explícitamente
                # en specs/05 §4 (que solo habla de timeout/5xx), pero se
                # tratan igual que un timeout -- son igualmente transitorios
                # y no deberían tumbar `/predicciones` (decisión de diseño
                # documentada en el reporte de BE-05).
                duracion_ms = int((time.monotonic() - inicio) * 1000)
                _log("WARNING", endpoint=endpoint, status="error", duracion_ms=duracion_ms)
                if intento < _MAX_ATTEMPTS - 1:
                    await asyncio.sleep(_BACKOFFS_SECONDS[intento])
                    continue
                _log("ERROR", endpoint=endpoint, evento="reintentos_agotados", status="error")
                raise _FetchFailed("error_conexion") from None

            duracion_ms = int((time.monotonic() - inicio) * 1000)

            if response.status_code == 200:
                _log("INFO", endpoint=endpoint, status=200, duracion_ms=duracion_ms)
                return response.json()

            codigo_weatherapi = _weatherapi_error_code(response)
            _log(
                "WARNING" if _es_reintentable(response.status_code, codigo_weatherapi) else "ERROR",
                endpoint=endpoint,
                status=response.status_code,
                duracion_ms=duracion_ms,
                codigo_weatherapi=codigo_weatherapi,
            )

            if _es_reintentable(response.status_code, codigo_weatherapi):
                if intento < _MAX_ATTEMPTS - 1:
                    await asyncio.sleep(_BACKOFFS_SECONDS[intento])
                    continue
                _log(
                    "ERROR",
                    endpoint=endpoint,
                    evento="reintentos_agotados",
                    status=response.status_code,
                    codigo_weatherapi=codigo_weatherapi,
                )
                raise _FetchFailed(f"http_{response.status_code}") from None

            # 4xx no reintentable (1002, 1006, 2006, 2007, 2008, u otro): se
            # registra ERROR una sola vez (arriba) y se degrada de inmediato.
            raise _FetchFailed(f"http_{response.status_code}") from None

        # Inalcanzable: el bucle siempre retorna o levanta dentro de sus
        # ramas, pero se deja explícito para que mypy/ruff no se quejen de
        # un `_fetch` sin retorno en todos los caminos.
        raise _FetchFailed("agotado")


def get_weather_client(settings: Settings = Depends(get_settings)) -> WeatherApiClient:
    """Factoría para `Depends(get_weather_client)` en los routers de BE-06.
    Equivalente a `Depends(WeatherApiClient)` (FastAPI también sabe resolver
    la clase directamente porque su `__init__` ya usa `Depends(get_settings)`
    como default), se deja como función explícita por legibilidad en las
    firmas de los routers."""
    return WeatherApiClient(settings)
