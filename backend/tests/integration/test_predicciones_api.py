"""QA-03: casos de integración IT-01..09, IT-12, IT-13 (parte `/predicciones`)
de `specs/08-plan-pruebas.md` §2.4.

Nacen de la spec (P1): `specs/04-api.md` §1-3 (contrato del endpoint),
`specs/05-integracion-weatherapi.md` (resiliencia/caché/errores) y
`specs/03-modelo-prediccion.md` §4 (advertencias). No son los smoke tests de
BE-06 (`tests/integration/test_routers_smoke.py`, que NO se toca): estos
cubren exactamente los casos obligatorios del plan de pruebas, con su ID en
el nombre y el requisito en el docstring (P2: trazabilidad).

Aislamiento: nunca se llama a la WeatherAPI real (siempre `respx`), y cada
test usa su propia SQLite temporal (`tmp_path`), igual que BE-06.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

import app.clock as clock_module
from app.clients.weatherapi import WeatherApiClient
from app.config import Settings, get_settings
from app.main import app, generar_dataset_inicial_si_vacio

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "weatherapi"
_FORECAST_URL = "https://api.weatherapi.com/v1/forecast.json"


def _load_fixture(name: str) -> dict:
    with (_FIXTURES / name).open(encoding="utf-8") as f:
        return json.load(f)


def _client_con_db(tmp_path: Path, *, weatherapi_key: str = "test-key-do-not-use") -> TestClient:
    """Mismo patrón que `tests/integration/test_routers_smoke.py`: dataset
    sintético ya generado en una SQLite temporal aislada, con
    `Depends(get_settings)` sobreescrito para toda la app."""
    db_path = str(tmp_path / "cueva-it.db")
    generar_dataset_inicial_si_vacio(db_path)

    settings = Settings(
        weatherapi_key=weatherapi_key,
        database_path=db_path,
        weather_cache_ttl_seconds=1800,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _limpiar_overrides() -> None:
    app.dependency_overrides.clear()


async def _no_op_sleep(*_args, **_kwargs) -> None:
    """Reemplazo de `asyncio.sleep` para que los tests de reintentos
    (specs/05 §4: backoff 0.5s/1s) no esperen tiempo real -- son
    deterministas y no dependen de temporizadores reales (specs/08: tests
    deterministas)."""
    return None


# --------------------------------------------------------------------------
# IT-01: GET /predicciones con forecast_ok.json -> 200, 3 elementos, fechas
# ascendentes, datos_sinteticos=true (RF-01..05, RF-11).
# --------------------------------------------------------------------------


@respx.mock
def test_IT_01_predicciones_forecast_ok_devuelve_3_dias_ascendentes(tmp_path: Path) -> None:
    """specs/08 IT-01 / RF-01..05: `GET /predicciones` sin `fecha` devuelve
    hoy, hoy+1, hoy+2 en orden ascendente, con `datos_sinteticos=true`."""
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
    predicciones = body["predicciones"]
    assert len(predicciones) == 3
    fechas = [date.fromisoformat(p["fecha"]) for p in predicciones]
    assert fechas == sorted(fechas)
    assert len(set(fechas)) == 3


# --------------------------------------------------------------------------
# IT-02: ?fecha=hoy+3 -> 422 FECHA_FUERA_DE_RANGO (RF-05).
# --------------------------------------------------------------------------


def test_IT_02_fecha_hoy_mas_3_da_422_fecha_fuera_de_rango(tmp_path: Path) -> None:
    """specs/08 IT-02 / RF-05: el pronóstico solo cubre hoy..hoy+2
    (specs/05 §1: WeatherAPI free da 3 días); hoy+3 está fuera de rango."""
    client = _client_con_db(tmp_path)
    hoy_mas_3 = clock_module.hoy_lima() + timedelta(days=3)
    try:
        response = client.get(f"/api/v1/predicciones?fecha={hoy_mas_3.isoformat()}")
    finally:
        _limpiar_overrides()

    assert response.status_code == 422
    assert response.json()["error"]["codigo"] == "FECHA_FUERA_DE_RANGO"


# --------------------------------------------------------------------------
# IT-03: ?fecha=2026-02-30 -> 422 FECHA_INVALIDA (RF-05).
# --------------------------------------------------------------------------


def test_IT_03_fecha_2026_02_30_da_422_fecha_invalida(tmp_path: Path) -> None:
    """specs/08 IT-03 / RF-05: 30 de febrero no existe en el calendario
    gregoriano -- `date.fromisoformat` lo rechaza."""
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/predicciones?fecha=2026-02-30")
    finally:
        _limpiar_overrides()

    assert response.status_code == 422
    assert response.json()["error"]["codigo"] == "FECHA_INVALIDA"


# --------------------------------------------------------------------------
# IT-04: timeout de WeatherAPI sin caché -> 200, clima_disponible=false,
# f_clima=1.0, advertencia CLIMA_NO_DISPONIBLE (RF-06, RNF-04).
# --------------------------------------------------------------------------


@respx.mock
def test_IT_04_timeout_sin_cache_degrada_con_f_clima_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """specs/08 IT-04 / RF-06, RNF-04: sin caché previa y con la WeatherAPI
    fuera (timeout en los 3 intentos), `/predicciones` sigue respondiendo
    200 -- nunca 503 -- con `clima_disponible=false`,
    `factores.clima.valor == 1.0` y la advertencia `CLIMA_NO_DISPONIBLE`."""
    monkeypatch.setattr("asyncio.sleep", _no_op_sleep)
    respx.get(_FORECAST_URL).mock(side_effect=httpx.TimeoutException("timeout sintético"))
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
        assert prediccion["factores"]["clima"]["valor"] == pytest.approx(1.0)
        codigos = {a["codigo"] for a in prediccion["advertencias"]}
        assert "CLIMA_NO_DISPONIBLE" in codigos


# --------------------------------------------------------------------------
# IT-05: WeatherAPI caída con caché de 2h -> 200, clima_disponible=true
# (usa caché) (specs/05 §4, RNF-04).
# --------------------------------------------------------------------------


@respx.mock
def test_IT_05_weatherapi_caida_con_cache_de_2h_usa_cache(tmp_path: Path) -> None:
    """specs/08 IT-05 / RF-06, RNF-04: aunque WeatherAPI esté caída, una
    caché de hasta 6h (specs/05 §4) hace que `/predicciones` siga con
    `clima_disponible=true`."""
    db_path = str(tmp_path / "cueva-it05.db")
    generar_dataset_inicial_si_vacio(db_path)
    settings = Settings(
        weatherapi_key="test-key-do-not-use",
        database_path=db_path,
        weather_cache_ttl_seconds=1800,
    )

    # Precarga la caché "fresca hace 2h" usando la misma clave que calcula el
    # cliente real (mismo patrón que tests/integration/test_weatherapi_client.py).
    seed_client = WeatherApiClient(settings)
    cache_key = seed_client._forecast_cache_key(3)
    cached_payload = _load_fixture("forecast_ok.json")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS weather_cache ("
            "cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL)"
        )
        fetched_at = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO weather_cache (cache_key, payload, fetched_at) "
            "VALUES (?, ?, ?)",
            (cache_key, json.dumps(cached_payload), fetched_at),
        )
        conn.commit()
    finally:
        conn.close()

    respx.get(_FORECAST_URL).mock(return_value=httpx.Response(500))
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    try:
        response = client.get("/api/v1/predicciones")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    body = response.json()
    for prediccion in body["predicciones"]:
        assert prediccion["clima_disponible"] is True
        assert prediccion["clima"] is not None


# --------------------------------------------------------------------------
# IT-06: dos llamadas seguidas -> WeatherAPI recibe 1 sola llamada (caché
# fresca) (RNF-08).
# --------------------------------------------------------------------------


@respx.mock
def test_IT_06_dos_llamadas_seguidas_solo_una_llamada_a_weatherapi(tmp_path: Path) -> None:
    """specs/08 IT-06 / RNF-08: la caché de `WEATHER_CACHE_TTL_SECONDS`
    evita repetir la llamada a WeatherAPI entre dos requests consecutivos al
    mismo cliente de test (misma DB temporal)."""
    route = respx.get(_FORECAST_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("forecast_ok.json"))
    )
    client = _client_con_db(tmp_path)
    try:
        primera = client.get("/api/v1/predicciones")
        segunda = client.get("/api/v1/predicciones")
    finally:
        _limpiar_overrides()

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert route.call_count == 1


# --------------------------------------------------------------------------
# IT-07: error 2007 (cuota) -> degrada; log ERROR sin la llave (specs/05 §5,
# RNF-05).
# --------------------------------------------------------------------------


@respx.mock
def test_IT_07_error_2007_cuota_degrada_y_loguea_error_sin_la_llave(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """specs/08 IT-07 / RF-06, RNF-05: 2007 (cuota mensual excedida) es un
    403 no reintentable (specs/05 §5) -- degrada sin 503 y el log de ERROR
    correspondiente nunca contiene la llave configurada."""
    secreto = "it07-secreto-de-prueba-no-usar"
    respx.get(_FORECAST_URL).mock(
        return_value=httpx.Response(403, json=_load_fixture("error_2007.json"))
    )
    client = _client_con_db(tmp_path, weatherapi_key=secreto)
    try:
        with caplog.at_level(logging.DEBUG):
            response = client.get("/api/v1/predicciones")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    body = response.json()
    for prediccion in body["predicciones"]:
        assert prediccion["clima_disponible"] is False

    registros_error = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert registros_error, "se esperaba al menos un log ERROR ante el fallo de WeatherAPI"
    assert secreto not in caplog.text
    for record in caplog.records:
        assert secreto not in record.getMessage()


# --------------------------------------------------------------------------
# IT-08: forecast_lluvia_extrema.json -> LLUVIA_EXTREMA y TORMENTA en el
# día 1 (specs/03 §4, RF-11).
# --------------------------------------------------------------------------


@respx.mock
def test_IT_08_lluvia_extrema_da_advertencias_lluvia_extrema_y_tormenta(tmp_path: Path) -> None:
    """specs/08 IT-08 / RF-11: `forecast_lluvia_extrema.json` trae
    `totalprecip_mm=55` (>= 50, specs/03 §4 vía `advertencias.lluvia_extrema_mm`
    de config/model.yaml) y código de condición 1276 (tormenta, en
    `clima.tormenta.codigos` de config/model.yaml) en horario de visita."""
    respx.get(_FORECAST_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("forecast_lluvia_extrema.json"))
    )
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/predicciones")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    dia1 = response.json()["predicciones"][0]
    codigos = {a["codigo"] for a in dia1["advertencias"]}
    assert "LLUVIA_EXTREMA" in codigos
    assert "TORMENTA" in codigos


# --------------------------------------------------------------------------
# IT-09: forecast_alerta.json -> ALERTA_OFICIAL con el headline real
# (specs/05 §3, RF-11).
# --------------------------------------------------------------------------


@respx.mock
def test_IT_09_forecast_alerta_da_advertencia_alerta_oficial_con_headline(tmp_path: Path) -> None:
    """specs/08 IT-09 / RF-11: `alerts.alert[].headline` de WeatherAPI se
    traduce en una `Advertencia` de código `ALERTA_OFICIAL` cuyo mensaje es
    el headline real (specs/05 §3)."""
    fixture = _load_fixture("forecast_alerta.json")
    headline_esperado = fixture["alerts"]["alert"][0]["headline"]
    respx.get(_FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture))
    client = _client_con_db(tmp_path)
    try:
        response = client.get("/api/v1/predicciones")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    dia1 = response.json()["predicciones"][0]
    alertas = [a for a in dia1["advertencias"] if a["codigo"] == "ALERTA_OFICIAL"]
    assert len(alertas) == 1
    assert alertas[0]["mensaje"] == headline_esperado


# --------------------------------------------------------------------------
# IT-12: reloj fijado a 2026-09-25 23:30 Lima (= 2026-09-26 04:30 UTC) ->
# "hoy" es 25 sep, no 26 (specs/00 §4: "Hoy" siempre es hoy en Lima).
# --------------------------------------------------------------------------


def test_IT_12_reloj_fijado_23_30_lima_hoy_es_25_no_26(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """specs/08 IT-12 / specs/00-constitucion.md §4 ("Hoy siempre es hoy en
    Lima, nunca en UTC"): con la hora real del sistema fijada a las 04:30
    UTC del 26 de septiembre de 2026 (23:30 del 25 en America/Lima, UTC-5),
    `hoy_lima()` debe devolver 25-sep, no 26-sep -- si devolviera 26 sería
    un error de conversión de zona horaria (calculando "hoy" en UTC).

    `app.clock.hoy_lima()`/`ayer_lima()` llaman a `datetime.now(LIMA_TZ)`
    importado como `from datetime import date, datetime, timedelta` dentro
    de `app/clock.py`: el binding relevante para `monkeypatch` es por tanto
    el nombre `datetime` **dentro del módulo `app.clock`**
    (`app.clock.datetime`), no `datetime.datetime` global ni
    `app.clock.hoy_lima` (eso solo reemplazaría la función, no probaría la
    conversión de zona horaria real). Se sustituye por una subclase que fija
    `.now(tz)` al instante UTC exacto del enunciado y delega todo lo demás
    (incluida la construcción de fechas/deltas dentro de `ayer_lima`) en la
    clase real `datetime`, para no tener que remockear cada uso."""

    instante_fijo_utc = datetime(2026, 9, 26, 4, 30, tzinfo=ZoneInfo("UTC"))

    class _RelojFijo(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return instante_fijo_utc.replace(tzinfo=None)
            return instante_fijo_utc.astimezone(tz)

    monkeypatch.setattr(clock_module, "datetime", _RelojFijo)

    # 1) Prueba directa y aislada del reloj (app.clock), sin pasar por la API.
    assert clock_module.hoy_lima() == date(2026, 9, 25)
    assert clock_module.ayer_lima() == date(2026, 9, 24)

    # 2) Prueba de extremo a extremo: el router usa el nombre `hoy_lima` que
    # importó en su propio namespace (`from app.clock import ... hoy_lima`),
    # así que basta con que `app.clock.hoy_lima` (ya parcheado arriba) siga
    # siendo la misma función -- el router la llama en tiempo de request, no
    # en tiempo de import, por lo que ve el reloj fijo sin parchear nada más.
    client = _client_con_db(tmp_path)
    try:
        with respx.mock:
            respx.get(_FORECAST_URL).mock(
                return_value=httpx.Response(200, json=_load_fixture("forecast_ok.json"))
            )
            response = client.get("/api/v1/predicciones?fecha=2026-09-25")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    assert response.json()["predicciones"][0]["fecha"] == "2026-09-25"


# --------------------------------------------------------------------------
# IT-13 (escenarios de /predicciones): ninguna respuesta ni log contiene el
# valor de WEATHERAPI_KEY (specs/00 P5, RNF-05).
# --------------------------------------------------------------------------


@respx.mock
def test_IT_13_exito_no_filtra_la_key_en_respuesta_ni_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """specs/08 IT-13 / P5, RNF-05: escenario "éxito" -- la llave configurada
    no debe aparecer ni en el cuerpo JSON de una respuesta 200 ni en ningún
    registro de log."""
    secreto = "it13-exito-secreto-no-usar"
    respx.get(_FORECAST_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("forecast_ok.json"))
    )
    client = _client_con_db(tmp_path, weatherapi_key=secreto)
    try:
        with caplog.at_level(logging.DEBUG):
            response = client.get("/api/v1/predicciones")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    assert secreto not in response.text
    assert secreto not in caplog.text


@respx.mock
def test_IT_13_timeout_no_filtra_la_key_en_respuesta_ni_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """specs/08 IT-13 / P5, RNF-05: escenario "timeout" (dispara reintentos
    y degradación, specs/05 §4) -- la llave tampoco debe filtrarse."""
    monkeypatch.setattr("asyncio.sleep", _no_op_sleep)
    secreto = "it13-timeout-secreto-no-usar"
    respx.get(_FORECAST_URL).mock(side_effect=httpx.TimeoutException("timeout sintético"))
    client = _client_con_db(tmp_path, weatherapi_key=secreto)
    try:
        with caplog.at_level(logging.DEBUG):
            response = client.get("/api/v1/predicciones")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200  # RF-06: nunca 503 por WeatherAPI
    assert secreto not in response.text
    assert secreto not in caplog.text


@respx.mock
def test_IT_13_error_2007_no_filtra_la_key_en_respuesta_ni_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """specs/08 IT-13 / P5, RNF-05: escenario "error 2007" (cuota
    excedida, specs/05 §5) -- la llave tampoco debe filtrarse, ni siquiera
    en el log ERROR que documenta el fallo."""
    secreto = "it13-2007-secreto-no-usar"
    respx.get(_FORECAST_URL).mock(
        return_value=httpx.Response(403, json=_load_fixture("error_2007.json"))
    )
    client = _client_con_db(tmp_path, weatherapi_key=secreto)
    try:
        with caplog.at_level(logging.DEBUG):
            response = client.get("/api/v1/predicciones")
    finally:
        _limpiar_overrides()

    assert response.status_code == 200
    assert secreto not in response.text
    assert secreto not in caplog.text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
