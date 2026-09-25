"""Router de `GET /api/v1/clima/actual` (RF-01, specs/04-api.md §1-3).

Único endpoint que sí puede devolver 503 `CLIMA_NO_DISPONIBLE` (a diferencia
de `/predicciones`, que degrada según RF-06): aquí no hay predicción de
respaldo que mostrar, así que si `WeatherApiClient.get_current()` no
consigue ni datos frescos ni caché, se lo decimos al cliente en vez de
inventar un clima.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.clients.weatherapi import (
    CurrentWeather,
    WeatherApiClient,
    WeatherUnavailableError,
    get_weather_client,
)
from app.clock import LIMA_TZ
from app.schemas import ClimaActual

router = APIRouter(tags=["clima"])


def _parse_last_updated(raw: str) -> datetime:
    """`CurrentWeather.last_updated` llega como `"YYYY-MM-DD HH:MM"` (hora
    local de Lima, sin offset, tal como la da WeatherAPI). Se le añade el
    offset de `America/Lima` para que `actualizado_en` sea un `date-time`
    ISO 8601 completo, tal como exige el contrato."""
    naive = datetime.strptime(raw, "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=LIMA_TZ)


def _to_clima_actual(current: CurrentWeather) -> ClimaActual:
    return ClimaActual(
        temp_c=current.temp_c,
        sensacion_c=current.feelslike_c,
        condicion=current.condition_text,
        icono_url=current.condition_icon or None,
        humedad=current.humidity,
        precipitacion_mm=current.precip_mm,
        actualizado_en=_parse_last_updated(current.last_updated),
    )


@router.get("/clima/actual", response_model=ClimaActual)
async def get_clima_actual(
    client: WeatherApiClient = Depends(get_weather_client),
) -> ClimaActual | JSONResponse:
    """RF-01: clima actual en la cueva. 503 `CLIMA_NO_DISPONIBLE` si
    WeatherAPI falla y no hay caché de hasta 6h (specs/04-api.md §3)."""
    try:
        current = await client.get_current()
    except WeatherUnavailableError:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "codigo": "CLIMA_NO_DISPONIBLE",
                    "mensaje": "No pudimos obtener el clima actual.",
                }
            },
        )

    return _to_clima_actual(current)
