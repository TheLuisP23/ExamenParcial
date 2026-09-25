"""QA-03: IT-10 de `specs/08-plan-pruebas.md` §2.4.

`GET /health` (RF-09): nunca debe llamar a WeatherAPI. No es el smoke test
de BE-06 (`tests/integration/test_routers_smoke.py`, que no cubre `/health`
en absoluto); este archivo es nuevo y propio de QA-03.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app, generar_dataset_inicial_si_vacio

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "weatherapi"
_FORECAST_URL = "https://api.weatherapi.com/v1/forecast.json"
_CURRENT_URL = "https://api.weatherapi.com/v1/current.json"


def _load_fixture(name: str) -> dict:
    with (_FIXTURES / name).open(encoding="utf-8") as f:
        return json.load(f)


@respx.mock
def test_IT_10_health_devuelve_ok_y_version_sin_llamar_a_weatherapi(tmp_path: Path) -> None:
    """specs/08 IT-10 / RF-09: `GET /health` responde 200
    `{status: "ok", version: APP_VERSION}` y jamás llama a WeatherAPI --
    se registran rutas mockeadas para `forecast`/`current` (si el endpoint
    las llamara, respx las contaría) y se verifica `call_count == 0` en
    ambas tras la petición."""
    version_esperada = "it10-version-de-prueba"
    ruta_forecast = respx.get(_FORECAST_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("forecast_ok.json"))
    )
    ruta_current = respx.get(_CURRENT_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("forecast_ok.json"))
    )

    db_path = str(tmp_path / "cueva-it10.db")
    generar_dataset_inicial_si_vacio(db_path)
    settings = Settings(
        weatherapi_key="test-key-do-not-use",
        database_path=db_path,
        app_version=version_esperada,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    try:
        response = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": version_esperada}
    assert ruta_forecast.call_count == 0
    assert ruta_current.call_count == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
