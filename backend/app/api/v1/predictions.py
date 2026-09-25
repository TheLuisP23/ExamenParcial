"""Router de `GET /api/v1/predicciones` (RF-01..05, RF-11, specs/04-api.md §1-3).

Traduce entre las capas de infraestructura (WeatherAPI, SQLite) y el dominio
puro (`app.domain.predictor.predict`), y de vuelta al contrato OpenAPI
(`app.schemas`). Solo valida y delega -- la fórmula, el desglose y las
advertencias base viven en `app.domain`.

Validación manual de `fecha` (specs/04-api.md §3): se declara como `str |
None` (sin `format: date` de Pydantic) para poder devolver el formato de
error `{error: {codigo, mensaje}}` del contrato en vez del 422 genérico de
FastAPI, que trae un `body` distinto.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.deps import get_repository
from app.clients.weatherapi import (
    DayForecast,
    WeatherApiClient,
    WeatherUnavailableError,
    get_weather_client,
)
from app.clock import LIMA_TZ, hoy_lima
from app.data.repository import VisitsRepository
from app.domain.config_loader import load_model_config
from app.domain.factors import ClimaInput, HourlyPoint
from app.domain.holidays import load_holiday_calendar
from app.domain.predictor import Desglose, predict
from app.domain.predictor import nivel_afluencia as calcular_nivel_afluencia
from app.schemas import (
    Advertencia,
    ClimaDia,
    Factor,
    Factores,
    Prediccion,
    PrediccionesResponse,
    Rango,
    Ubicacion,
)

router = APIRouter(tags=["predicciones"])

# specs/03 §4: tabla código -> mensaje fijo. `ALERTA_OFICIAL` no está aquí
# porque su mensaje es el `headline` dinámico de WeatherAPI (se arma en
# `_advertencias_respuesta`), no un texto fijo de esta tabla.
_ADVERTENCIA_MENSAJES: dict[str, str] = {
    "LLUVIA_EXTREMA": "Lluvia muy intensa: posible cierre o restricción de senderos.",
    "TORMENTA": "Tormenta eléctrica pronosticada en horario de visita.",
    "CLIMA_NO_DISPONIBLE": "No pudimos obtener el clima.",
}


def _find_location_config_dir() -> Path:
    """Localiza el directorio `config/` (hermano de `backend/`). Copia local
    de la misma búsqueda que ya existe en `app.domain.config_loader` y en
    `app.clients.weatherapi` (patrón establecido por BE-02/BE-05: cada capa
    resuelve `config/` de forma independiente en vez de importar un símbolo
    privado de otro módulo)."""
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


@lru_cache
def _load_ubicacion() -> Ubicacion:
    """`config/location.yaml` (P7): nombre/lat/lon para `ubicacion` en
    `PrediccionesResponse`."""
    path = _find_location_config_dir() / "location.yaml"
    with path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return Ubicacion(nombre=str(cfg["nombre"]), lat=float(cfg["lat"]), lon=float(cfg["lon"]))


def _to_clima_input(day: DayForecast) -> ClimaInput:
    """`DayForecast` (cliente WeatherAPI, BE-05) -> `ClimaInput` (dominio,
    BE-02/03). El cliente no conoce el dominio a propósito (ver docstring de
    `app.clients.weatherapi`); este mapeo es responsabilidad del router."""
    return ClimaInput(
        precip_mm=day.totalprecip_mm,
        maxtemp_c=day.maxtemp_c,
        chance_of_rain=day.daily_chance_of_rain,
        condition_code=day.condition_code,
        hourly=[
            HourlyPoint(
                hour=h.hour, chance_of_rain=h.chance_of_rain, condition_code=h.condition_code
            )
            for h in day.hourly
        ],
    )


def _to_clima_dia(day: DayForecast) -> ClimaDia:
    """`DayForecast` -> componente `ClimaDia` del contrato."""
    return ClimaDia(
        condicion=day.condition_text,
        codigo_condicion=day.condition_code,
        icono_url=day.condition_icon or None,
        temp_max_c=day.maxtemp_c,
        temp_min_c=day.mintemp_c,
        precipitacion_mm=day.totalprecip_mm,
        probabilidad_lluvia=day.daily_chance_of_rain,
    )


def _to_factores(desglose: Desglose) -> Factores:
    """`Desglose` (dominio) -> componente `Factores` del contrato."""
    return Factores(
        base_diaria=desglose.base_diaria,
        temporada=Factor(valor=desglose.temporada.valor, razon=desglose.temporada.razon),
        dia_semana=Factor(valor=desglose.dia_semana.valor, razon=desglose.dia_semana.razon),
        feriado=Factor(valor=desglose.feriado.valor, razon=desglose.feriado.razon),
        clima=Factor(valor=desglose.clima.valor, razon=desglose.clima.razon),
        tope_capacidad_aplicado=desglose.tope_capacidad_aplicado,
    )


def _advertencias_respuesta(codigos: list[str], alert_headlines: list[str]) -> list[Advertencia]:
    """Códigos de `predict()` (`LLUVIA_EXTREMA`/`TORMENTA`/`CLIMA_NO_DISPONIBLE`)
    + `ALERTA_OFICIAL` (specs/03 §4).

    Decisión de criterio (no fijada por la spec): `ALERTA_OFICIAL` se emite
    **una `Advertencia` por cada `headline`** de `ForecastResult.alert_headlines`
    (no un único mensaje agregado), porque cada alerta oficial de WeatherAPI
    es un texto independiente y el frontend puede querer listarlas todas. Se
    añade a **todas** las predicciones del payload que sí obtuvieron
    pronóstico fresco (WeatherAPI no indica a qué día específico aplica cada
    alerta dentro de la ventana consultada); si el pronóstico completo falla
    (`WeatherUnavailableError`), `alert_headlines` llega vacía y por tanto no
    se añade ninguna `ALERTA_OFICIAL` (coherente con la degradación de RF-06).
    """
    advertencias = [
        Advertencia(codigo=codigo, mensaje=_ADVERTENCIA_MENSAJES[codigo]) for codigo in codigos
    ]
    advertencias.extend(
        Advertencia(codigo="ALERTA_OFICIAL", mensaje=headline) for headline in alert_headlines
    )
    return advertencias


def _error_fecha_invalida(fecha_cruda: str) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "codigo": "FECHA_INVALIDA",
                "mensaje": f"'{fecha_cruda}' no es una fecha válida (formato esperado YYYY-MM-DD).",
            }
        },
    )


def _error_fecha_fuera_de_rango(hoy: date, hoy_mas_2: date) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "codigo": "FECHA_FUERA_DE_RANGO",
                "mensaje": (
                    f"La fecha debe estar entre {hoy.isoformat()} y {hoy_mas_2.isoformat()}."
                ),
            }
        },
    )


@router.get("/predicciones", response_model=PrediccionesResponse)
async def get_predicciones(
    fecha: str | None = Query(
        None, description="Fecha única YYYY-MM-DD. Si se omite, hoy..hoy+2."
    ),
    weather_client: WeatherApiClient = Depends(get_weather_client),
    repo: VisitsRepository = Depends(get_repository),
) -> PrediccionesResponse | JSONResponse:
    """RF-01..05, RF-11: predicción de 1 día (`?fecha=`) o de hoy..hoy+2
    (sin parámetro), en America/Lima. **Nunca** devuelve 503 por WeatherAPI
    (RF-06): ante `WeatherUnavailableError`, todas las predicciones del
    payload degradan con `clima_disponible=false` / `clima=null`."""
    hoy = hoy_lima()
    hoy_mas_2 = hoy + timedelta(days=2)

    if fecha is not None:
        try:
            fecha_parsed = date.fromisoformat(fecha)
        except ValueError:
            return _error_fecha_invalida(fecha)
        if not (hoy <= fecha_parsed <= hoy_mas_2):
            return _error_fecha_fuera_de_rango(hoy, hoy_mas_2)
        fechas = [fecha_parsed]
    else:
        fechas = [hoy + timedelta(days=i) for i in range(3)]

    base_diaria = repo.get_base_diaria() or 0.0
    percentiles = repo.percentiles()
    holidays = load_holiday_calendar()

    dias_necesarios = (fechas[-1] - hoy).days + 1
    dias_por_fecha: dict[date, DayForecast] = {}
    alert_headlines: list[str] = []
    try:
        forecast = await weather_client.get_forecast(days=dias_necesarios)
        dias_por_fecha = {d.date: d for d in forecast.days}
        alert_headlines = forecast.alert_headlines
    except WeatherUnavailableError:
        pass  # RF-06: degrada, `dias_por_fecha` queda vacío => clima=None en todas.

    predicciones: list[Prediccion] = []
    for f in fechas:
        day_forecast = dias_por_fecha.get(f)
        clima_input = _to_clima_input(day_forecast) if day_forecast is not None else None

        prediccion_dominio = predict(f, clima_input, base_diaria, holidays)
        nivel = calcular_nivel_afluencia(
            prediccion_dominio.visitantes_estimados,
            percentiles.p25,
            percentiles.p75,
            percentiles.p95,
        )

        predicciones.append(
            Prediccion(
                fecha=f,
                visitantes_estimados=prediccion_dominio.visitantes_estimados,
                rango=Rango(min=prediccion_dominio.rango_min, max=prediccion_dominio.rango_max),
                nivel_afluencia=nivel,
                clima_disponible=day_forecast is not None,
                clima=_to_clima_dia(day_forecast) if day_forecast is not None else None,
                factores=_to_factores(prediccion_dominio.factores),
                advertencias=_advertencias_respuesta(
                    prediccion_dominio.advertencias, alert_headlines
                ),
            )
        )

    cfg = load_model_config()
    return PrediccionesResponse(
        ubicacion=_load_ubicacion(),
        version_modelo=str(cfg["version_modelo"]),
        datos_sinteticos=True,
        generado_en=datetime.now(LIMA_TZ),
        predicciones=predicciones,
        atribucion="Powered by WeatherAPI.com",
    )
