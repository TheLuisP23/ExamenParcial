"""Test propio de BE-07 (red de seguridad adicional a la de QA-03/IT-13):
verifica con `caplog` que `WEATHERAPI_KEY` nunca aparece en ningún registro
de log capturado, ni siquiera si un logger futuro cometiera el error de
incluirla explícitamente en un mensaje o en un campo `extra`.

No es el test de contrato de QA-03 (ese se escribe en una tarea posterior
contra los routers); este es el test "unitario de infraestructura" del
propio filtro de redacción (`app.main.RedactWeatherApiKeyFilter`) y de la
disciplina de `app.clients.weatherapi` (BE-05), usando las fixtures ya
creadas por QA-01 en `tests/fixtures/weatherapi/` vía `respx`. **Nunca**
llama a la WeatherAPI real.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest
import respx

from app.clients.weatherapi import WeatherApiClient
from app.config import Settings
from app.main import settings as app_settings

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "weatherapi"
_FORECAST_URL = "https://api.weatherapi.com/v1/forecast.json"


def _load_fixture(name: str) -> dict:
    with (_FIXTURES / name).open(encoding="utf-8") as f:
        return json.load(f)


def _run(coro):
    return asyncio.run(coro)


def test_el_filtro_redacta_una_fuga_sintetica_de_la_key_en_el_mensaje(caplog) -> None:
    """Simula el "error humano futuro" contra el que RNF-05/P5 pide
    blindarse: un logger que por accidente incluye la llave literal en el
    mensaje. El filtro global instalado en `app.main._configure_logging`
    debe redactarla igual, sin importar qué logger la emitió."""
    secreto = app_settings.weatherapi_key
    assert secreto  # la fixture de tests/conftest.py garantiza que no está vacía

    with caplog.at_level(logging.DEBUG):
        logging.getLogger("cueva.weatherapi").warning(
            "URL de depuración (no debería loguearse así): %s?key=%s",
            "https://api.weatherapi.com/v1/forecast.json",
            secreto,
        )

    assert secreto not in caplog.text
    assert "***REDACTED***" in caplog.text
    for record in caplog.records:
        assert secreto not in record.getMessage()
        assert secreto not in record.msg


def test_el_filtro_redacta_una_fuga_sintetica_de_la_key_en_extra(caplog) -> None:
    """Igual que el test anterior, pero la fuga ocurre en un campo `extra`
    (p. ej. `ruta`) en vez de en el mensaje principal -- el otro caso que
    pide cubrir la tarea."""
    secreto = app_settings.weatherapi_key
    assert secreto

    with caplog.at_level(logging.DEBUG):
        logging.getLogger("cueva.access").info(
            "acceso",
            extra={"ruta": f"/clima/actual?key={secreto}", "status": 200},
        )

    assert secreto not in caplog.text
    for record in caplog.records:
        assert secreto not in getattr(record, "ruta", "")


@respx.mock
def test_llamadas_reales_del_cliente_weatherapi_nunca_filtran_la_key(caplog, tmp_path) -> None:
    """Extremo a extremo (RNF-05, escenario de IT-13 futuro): con el cliente
    real de BE-05 mockeado vía `respx` -- tanto en éxito como en un fallo que
    dispara reintentos y degradación -- la llave configurada en el test no
    debe aparecer en ningún registro capturado por `caplog`."""
    secreto = "clave-de-prueba-para-caplog-no-usar"
    settings = Settings(
        weatherapi_key=secreto,
        database_path=str(tmp_path / "cueva-test.db"),
    )
    client = WeatherApiClient(settings)

    fixture_ok = _load_fixture("forecast_ok.json")
    route = respx.get(_FORECAST_URL)
    route.side_effect = [
        httpx.Response(500, json={"error": {"code": 9997, "message": "boom"}}),
        httpx.Response(200, json=fixture_ok),
    ]

    with caplog.at_level(logging.DEBUG):
        resultado = _run(client.get_forecast(days=3))

    assert resultado.source == "api"
    assert secreto not in caplog.text
    for record in caplog.records:
        assert secreto not in record.getMessage()
        for valor in record.__dict__.values():
            if isinstance(valor, str):
                assert secreto not in valor


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
