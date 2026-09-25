"""Smoke tests propios de BE-06 para los routers `/predicciones`,
`/clima/actual`, `/historico/mensual` y `/modelo`.

No son los tests de contrato exhaustivos de QA-03 (esa tarea es la
siguiente en la trazabilidad, specs/10): solo verifican que cada endpoint
arranca, delega correctamente en `app.domain`/`app.data`/`app.clients` y
responde con la forma esperada del contrato, incluyendo los casos de error
de validación manual (`FECHA_INVALIDA`, `FECHA_FUERA_DE_RANGO`,
`PARAMETRO_INVALIDO`, `CLIMA_NO_DISPONIBLE`). **Nunca** llaman a la
WeatherAPI real: usan `respx` contra la fixture `forecast_ok.json` (que ya
incluye un bloque `current` válido, reutilizable para `/clima/actual`).
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from app.clock import hoy_lima
from app.config import Settings, get_settings
from app.main import app, generar_dataset_inicial_si_vacio

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "weatherapi"
_FORECAST_URL = "https://api.weatherapi.com/v1/forecast.json"
_CURRENT_URL = "https://api.weatherapi.com/v1/current.json"


def _load_fixture(name: str) -> dict:
    with (_FIXTURES / name).open(encoding="utf-8") as f:
        return json.load(f)


def _client_con_db(tmp_path: Path) -> TestClient:
    """`TestClient` con un dataset sintético ya generado en una SQLite
    temporal (aislada de `./cueva.db`) y `Depends(get_settings)` apuntando a
    ella para toda la app (routers y `WeatherApiClient` comparten la misma
    `Settings`, así que basta con sobreescribir esa única dependencia)."""
    db_path = str(tmp_path / "cueva-smoke.db")
    generar_dataset_inicial_si_vacio(db_path)

    settings = Settings(
        weatherapi_key="test-key-do-not-use",
        database_path=db_path,
        weather_cache_ttl_seconds=1800,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _limpiar_overrides() -> None:
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# GET /predicciones (RF-01..05, RF-11).
# --------------------------------------------------------------------------


@respx.mock
def test_predicciones_sin_fecha_devuelve_3_dias(tmp_path: Path) -> None:
    respx.get(_FORECAST_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("forecast_ok.json"))
    )
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/predicciones")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["datos_sinteticos"] is True
    assert body["atribucion"] == "Powered by WeatherAPI.com"
    assert body["version_modelo"] == "reglas-v1"
    assert len(body["predicciones"]) == 3
    hoy = hoy_lima()
    assert body["predicciones"][0]["fecha"] == hoy.isoformat()
    assert body["predicciones"][0]["clima_disponible"] is True
    assert body["predicciones"][0]["clima"]["condicion"]
    assert "factores" in body["predicciones"][0]
    assert body["predicciones"][0]["factores"]["tope_capacidad_aplicado"] in (True, False)


@respx.mock
def test_predicciones_con_fecha_valida_devuelve_1_dia(tmp_path: Path) -> None:
    respx.get(_FORECAST_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("forecast_ok.json"))
    )
    client = _client_con_db(tmp_path)
    hoy = hoy_lima()
    try:
        response = client.get(f"/api/v1/predicciones?fecha={hoy.isoformat()}")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    body = response.json()
    assert len(body["predicciones"]) == 1
    assert body["predicciones"][0]["fecha"] == hoy.isoformat()


def test_predicciones_fecha_con_formato_invalido_da_422_fecha_invalida(tmp_path: Path) -> None:
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/predicciones?fecha=2026-02-30")
    finally:
        _limpiar_overrides()

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "codigo": "FECHA_INVALIDA",
            "mensaje": response.json()["error"]["mensaje"],
        }
    }


def test_predicciones_fecha_pasada_da_422_fecha_fuera_de_rango(tmp_path: Path) -> None:
    client = _client_con_db(tmp_path)
    ayer = hoy_lima() - timedelta(days=1)
    try:
        response = client.get(f"/api/v1/predicciones?fecha={ayer.isoformat()}")
    finally:
        _limpiar_overrides()

    assert response.status_code == 422
    assert response.json()["error"]["codigo"] == "FECHA_FUERA_DE_RANGO"


@respx.mock
def test_predicciones_degrada_sin_503_cuando_weatherapi_falla(tmp_path: Path) -> None:
    """RF-06: `/predicciones` nunca devuelve 503 por WeatherAPI."""
    respx.get(_FORECAST_URL).mock(return_value=httpx.Response(500))
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/predicciones")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    body = response.json()
    for prediccion in body["predicciones"]:
        assert prediccion["clima_disponible"] is False
        assert prediccion["clima"] is None
        assert {"codigo": "CLIMA_NO_DISPONIBLE", "mensaje": "No pudimos obtener el clima."} in (
            prediccion["advertencias"]
        )


# --------------------------------------------------------------------------
# GET /clima/actual (RF-01).
# --------------------------------------------------------------------------


@respx.mock
def test_clima_actual_ok(tmp_path: Path) -> None:
    respx.get(_CURRENT_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("forecast_ok.json"))
    )
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/clima/actual")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["temp_c"], (int, float))
    assert body["condicion"]
    assert isinstance(body["humedad"], int)
    assert body["actualizado_en"]


@respx.mock
def test_clima_actual_503_cuando_weatherapi_no_disponible(tmp_path: Path) -> None:
    respx.get(_CURRENT_URL).mock(return_value=httpx.Response(500))
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/clima/actual")
    finally:
        _limpiar_overrides()

    assert response.status_code == 503
    assert response.json()["error"]["codigo"] == "CLIMA_NO_DISPONIBLE"


# --------------------------------------------------------------------------
# GET /historico/mensual (RF-08).
# --------------------------------------------------------------------------


def test_historico_mensual_default_devuelve_serie_no_vacia(tmp_path: Path) -> None:
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/historico/mensual")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["datos_sinteticos"] is True
    assert len(body["serie"]) > 0
    primero = body["serie"][0]
    assert set(primero.keys()) == {"mes", "visitantes", "promedio_diario"}


def test_historico_mensual_meses_fuera_de_rango_da_422(tmp_path: Path) -> None:
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/historico/mensual?meses=0")
    finally:
        _limpiar_overrides()

    assert response.status_code == 422
    assert response.json()["error"]["codigo"] == "PARAMETRO_INVALIDO"


def test_historico_mensual_meses_no_entero_da_422(tmp_path: Path) -> None:
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/historico/mensual?meses=abc")
    finally:
        _limpiar_overrides()

    assert response.status_code == 422
    assert response.json()["error"]["codigo"] == "PARAMETRO_INVALIDO"


# --------------------------------------------------------------------------
# GET /modelo (P3).
# --------------------------------------------------------------------------


def test_modelo_devuelve_version_y_coeficientes_no_vacios(tmp_path: Path) -> None:
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/modelo")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["version_modelo"] == "reglas-v1"
    assert body["capacidad_diaria"] == 1500
    assert body["base_diaria"] > 0
    assert body["coeficientes"]  # no vacío (P3: transparencia del modelo)
    assert "temporada" in body["coeficientes"]
