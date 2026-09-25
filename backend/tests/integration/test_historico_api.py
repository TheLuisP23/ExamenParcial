"""QA-03: IT-11 de `specs/08-plan-pruebas.md` §2.4.

`GET /historico/mensual` (RF-08): `meses` fuera de 1..36 -> 422
`PARAMETRO_INVALIDO`. No es el smoke test de BE-06
(`tests/integration/test_routers_smoke.py`, que ya cubre `meses=0` y
`meses=abc` pero no el ID de este caso obligatorio); este archivo es nuevo y
propio de QA-03. No llama a WeatherAPI (el endpoint no la usa), pero de
todas formas nunca hace falta red real: el dataset sintético se genera
localmente en una SQLite temporal.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app, generar_dataset_inicial_si_vacio


def test_IT_11_historico_meses_37_da_422_parametro_invalido(tmp_path: Path) -> None:
    """specs/08 IT-11 / RF-08: `meses` debe estar entre 1 y 36
    (specs/04-api.md §1); 37 excede el máximo."""
    db_path = str(tmp_path / "cueva-it11.db")
    generar_dataset_inicial_si_vacio(db_path)
    settings = Settings(weatherapi_key="test-key-do-not-use", database_path=db_path)
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    try:
        response = client.get("/api/v1/historico/mensual?meses=37")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error"]["codigo"] == "PARAMETRO_INVALIDO"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
