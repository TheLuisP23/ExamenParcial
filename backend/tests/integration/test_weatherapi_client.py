"""Tests propios de BE-05 para `app.clients.weatherapi` (red de seguridad).

No son los tests de integración/contrato de QA-03 (IT-01..13, que se
escriben contra los routers en una tarea posterior): estos son tests
"unitarios de infraestructura" que valida el propio agente backend antes de
entregar el cliente, usando `respx` contra las fixtures ya creadas por QA-01
en `tests/fixtures/weatherapi/`. **Nunca** llaman a la WeatherAPI real.

Cubren, sobre RF-01/RF-06 (specs/05 §3-§5): parseo de campos, caché fresca
(no repite llamadas dentro del TTL), reintentos (5xx y el caso especial
9999), no-reintento ante 4xx "reales", degradación con caché de hasta 6h y
`WeatherUnavailableError` cuando no hay ni API ni caché utilizable.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from app.clients.weatherapi import WeatherApiClient, WeatherUnavailableError
from app.config import Settings

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "weatherapi"
_FORECAST_URL = "https://api.weatherapi.com/v1/forecast.json"
_CURRENT_URL = "https://api.weatherapi.com/v1/current.json"


def _load_fixture(name: str) -> dict:
    with (_FIXTURES / name).open(encoding="utf-8") as f:
        return json.load(f)


def _settings(tmp_path: Path, *, ttl_seconds: int = 1800) -> Settings:
    return Settings(
        weatherapi_key="test-key-do-not-use",
        database_path=str(tmp_path / "cueva-test.db"),
        weather_cache_ttl_seconds=ttl_seconds,
    )


def _seed_cache(database_path: str, cache_key: str, payload: dict, *, age: timedelta) -> None:
    conn = sqlite3.connect(database_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS weather_cache ("
            "cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL)"
        )
        fetched_at = (datetime.now(UTC) - age).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO weather_cache (cache_key, payload, fetched_at) "
            "VALUES (?, ?, ?)",
            (cache_key, json.dumps(payload), fetched_at),
        )
        conn.commit()
    finally:
        conn.close()


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# Parseo de campos (specs/05 §3).
# --------------------------------------------------------------------------


@respx.mock
def test_get_forecast_ok_parsea_los_3_dias(tmp_path: Path) -> None:
    fixture = _load_fixture("forecast_ok.json")
    respx.get(_FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture))
    client = WeatherApiClient(_settings(tmp_path))

    result = _run(client.get_forecast(days=3))

    assert result.source == "api"
    assert len(result.days) == 3
    dia1 = result.days[0]
    assert dia1.date.isoformat() == "2026-09-25"
    assert dia1.totalprecip_mm == pytest.approx(3.2)
    assert dia1.daily_chance_of_rain == 55
    assert dia1.maxtemp_c == pytest.approx(28.5)
    assert dia1.mintemp_c == pytest.approx(20.1)
    assert dia1.condition_code == 1063
    assert dia1.condition_icon.startswith("https://")
    assert len(dia1.hourly) == 24
    assert [p.hour for p in dia1.hourly] == list(range(24))
    assert dia1.hourly[8].chance_of_rain == 55


@respx.mock
def test_get_forecast_lluvia_extrema(tmp_path: Path) -> None:
    fixture = _load_fixture("forecast_lluvia_extrema.json")
    respx.get(_FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture))
    client = WeatherApiClient(_settings(tmp_path))

    result = _run(client.get_forecast(days=3))

    dia1 = result.days[0]
    assert dia1.totalprecip_mm == pytest.approx(55.0)
    assert dia1.condition_code == 1276


@respx.mock
def test_get_forecast_alerta_headlines(tmp_path: Path) -> None:
    fixture = _load_fixture("forecast_alerta.json")
    respx.get(_FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture))
    client = WeatherApiClient(_settings(tmp_path))

    result = _run(client.get_forecast(days=3))

    assert result.alert_headlines == ["Aviso por lluvias intensas en Huanuco"]


@respx.mock
def test_get_current_ok(tmp_path: Path) -> None:
    fixture = _load_fixture("forecast_ok.json")  # también trae bloque "current"
    respx.get(_CURRENT_URL).mock(return_value=httpx.Response(200, json=fixture))
    client = WeatherApiClient(_settings(tmp_path))

    result = _run(client.get_current())

    assert result.source == "api"
    assert result.temp_c == pytest.approx(26.0)
    assert result.humidity == 78
    assert result.condition_code == 1003
    assert result.condition_icon == "https://cdn.weatherapi.com/weather/64x64/day/116.png"
    assert result.last_updated == "2026-09-25 09:30"


# --------------------------------------------------------------------------
# Caché fresca: no repite llamadas dentro del TTL (RNF-08).
# --------------------------------------------------------------------------


@respx.mock
def test_cache_fresca_evita_segunda_llamada(tmp_path: Path) -> None:
    fixture = _load_fixture("forecast_ok.json")
    route = respx.get(_FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture))
    client = WeatherApiClient(_settings(tmp_path, ttl_seconds=1800))

    primero = _run(client.get_forecast(days=3))
    segundo = _run(client.get_forecast(days=3))

    assert primero.source == "api"
    assert segundo.source == "cache"
    assert route.call_count == 1


# --------------------------------------------------------------------------
# Reintentos (specs/05 §4-§5).
# --------------------------------------------------------------------------


@respx.mock
def test_reintenta_ante_5xx_y_luego_tiene_exito(tmp_path: Path) -> None:
    fixture = _load_fixture("forecast_ok.json")
    route = respx.get(_FORECAST_URL)
    route.side_effect = [
        httpx.Response(503, json={"error": {"code": 9998, "message": "unavailable"}}),
        httpx.Response(200, json=fixture),
    ]
    client = WeatherApiClient(_settings(tmp_path))

    result = _run(client.get_forecast(days=3))

    assert result.source == "api"
    assert route.call_count == 2


@respx.mock
def test_reintenta_ante_codigo_9999_pese_a_ser_400(tmp_path: Path) -> None:
    """specs/05 §5: 9999/400 es la unica excepcion a 'nunca reintentar 4xx'."""
    fixture = _load_fixture("forecast_ok.json")
    route = respx.get(_FORECAST_URL)
    route.side_effect = [
        httpx.Response(400, json={"error": {"code": 9999, "message": "internal"}}),
        httpx.Response(200, json=fixture),
    ]
    client = WeatherApiClient(_settings(tmp_path))

    result = _run(client.get_forecast(days=3))

    assert result.source == "api"
    assert route.call_count == 2


@respx.mock
def test_no_reintenta_ante_2007_cuota_excedida(tmp_path: Path) -> None:
    """specs/05 §5: 2007/403 (cuota) no es reintentable -- un solo intento."""
    fixture = _load_fixture("error_2007.json")
    route = respx.get(_FORECAST_URL).mock(return_value=httpx.Response(403, json=fixture))
    client = WeatherApiClient(_settings(tmp_path))

    with pytest.raises(WeatherUnavailableError):
        _run(client.get_forecast(days=3))

    assert route.call_count == 1


# --------------------------------------------------------------------------
# Degradación con caché de hasta 6h, y sin caché (specs/05 §4, RF-06).
# --------------------------------------------------------------------------


@respx.mock
def test_usa_cache_de_2h_cuando_la_api_falla(tmp_path: Path) -> None:
    settings = _settings(tmp_path, ttl_seconds=1800)  # TTL 30 min
    client = WeatherApiClient(settings)
    cache_key = client._forecast_cache_key(3)
    cached_payload = _load_fixture("forecast_ok.json")
    _seed_cache(settings.database_path, cache_key, cached_payload, age=timedelta(hours=2))

    fixture_2006 = _load_fixture("error_2006.json")
    route = respx.get(_FORECAST_URL).mock(return_value=httpx.Response(401, json=fixture_2006))

    result = _run(client.get_forecast(days=3))

    assert result.source == "cache"
    assert len(result.days) == 3
    assert route.call_count == 1  # 401/2006 no es reintentable


@respx.mock
def test_cache_de_mas_de_6h_no_se_usa_y_degrada(tmp_path: Path) -> None:
    settings = _settings(tmp_path, ttl_seconds=1800)
    client = WeatherApiClient(settings)
    cache_key = client._forecast_cache_key(3)
    cached_payload = _load_fixture("forecast_ok.json")
    _seed_cache(settings.database_path, cache_key, cached_payload, age=timedelta(hours=7))

    fixture_2006 = _load_fixture("error_2006.json")
    respx.get(_FORECAST_URL).mock(return_value=httpx.Response(401, json=fixture_2006))

    with pytest.raises(WeatherUnavailableError) as exc_info:
        _run(client.get_forecast(days=3))

    assert exc_info.value.endpoint == "forecast"


@respx.mock
def test_sin_api_y_sin_cache_levanta_weather_unavailable(tmp_path: Path) -> None:
    """RF-06: esta es la señal que el router usa para degradar `/predicciones`
    con `clima=None` (f_clima=1.0) sin romper la respuesta."""
    route = respx.get(_FORECAST_URL).mock(
        return_value=httpx.Response(500, json={"error": {"code": 9997, "message": "boom"}})
    )
    client = WeatherApiClient(_settings(tmp_path))

    with pytest.raises(WeatherUnavailableError):
        _run(client.get_forecast(days=3))

    assert route.call_count == 3  # intento inicial + 2 reintentos agotados


# --------------------------------------------------------------------------
# Seguridad: la llave nunca aparece en ninguna excepción levantada.
# --------------------------------------------------------------------------


@respx.mock
def test_la_llave_nunca_aparece_en_la_excepcion(tmp_path: Path) -> None:
    respx.get(_FORECAST_URL).mock(return_value=httpx.Response(500))
    settings = _settings(tmp_path)
    client = WeatherApiClient(settings)

    with pytest.raises(WeatherUnavailableError) as exc_info:
        _run(client.get_forecast(days=3))

    assert settings.weatherapi_key not in str(exc_info.value)
    assert settings.weatherapi_key not in repr(exc_info.value)
    cause = exc_info.value.__cause__
    assert cause is None  # `from None`: no arrastra el request/URL de httpx
