"""QA-03: validación de contrato con Schemathesis sobre `specs/openapi.yaml`
(specs/08-plan-pruebas.md §1, fila "Contrato": "Que las respuestas reales
cumplan el esquema").

`specs/openapi.yaml` es la fuente de verdad (specs/04-api.md §0: "si el
código y openapi.yaml difieren, el código está mal"), no el
`/api/v1/openapi.json` que FastAPI autogenera -- por eso el esquema se carga
con `schemathesis.openapi.from_path("../specs/openapi.yaml")` en vez de
`from_asgi`. La app ASGI se ejecuta en proceso (sin servidor HTTP real):
se le asigna `schema.app = app` y un `base_url` ficticio
(`http://testserver/api/v1`, igual que el `TestClient` de Starlette), y
Schemathesis despacha cada caso generado a través del transporte ASGI
in-process de la librería.

Aislamiento: Hypothesis genera valores aleatorios de `fecha`/`meses`
(incluye ejecutar `/predicciones` y `/clima/actual`, que sí llaman a
WeatherAPI), así que un mock de `respx` permanece activo durante **toda**
la sesión de fuzzing, interceptando `forecast.json`/`current.json` con la
fixture `forecast_ok.json` para que ningún caso generado intente salir a
Internet. `pytest.ini`/`pyproject.toml` no registra el plugin
`pytest-schemathesis`: este archivo usa la API programática de Hypothesis
(`@given(case=schema.as_strategy())`) en vez del decorador
`schema.parametrize()`, para poder envolver toda la ejecución en un único
`with respx.mock(...):` y en un único dataset sintético (necesarios de todas
formas para que la app funcione), y agregar todos los fallos encontrados en
un solo mensaje de aserción en vez de una excepción por caso.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
import schemathesis.openapi as op
import schemathesis.specs.openapi.checks as openapi_checks
from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings

from app.clients.weatherapi import WeatherApiClient
from app.clock import ayer_lima
from app.config import Settings, get_settings
from app.data.generator import generate
from app.data.repository import VisitsRepository
from app.domain.config_loader import load_model_config
from app.domain.holidays import load_holiday_calendar
from app.main import app

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "weatherapi"
_FORECAST_URL = "https://api.weatherapi.com/v1/forecast.json"
_CURRENT_URL = "https://api.weatherapi.com/v1/current.json"
_OPENAPI_PATH = Path(__file__).resolve().parents[3] / "specs" / "openapi.yaml"

# specs/08 exige tests deterministas con semilla fija: `derandomize=True` usa
# siempre la misma secuencia de casos generados por Hypothesis para esta
# función de test (no depende de un reloj ni de aleatoriedad real), y
# `max_examples` se mantiene moderado para que el fuzzing corra en segundos
# en CI sin perder cobertura de las 5 operaciones del contrato.
_MAX_EXAMPLES = 60


def _load_fixture(name: str) -> dict:
    with (_FIXTURES / name).open(encoding="utf-8") as f:
        return json.load(f)


def _build_schema():
    """Carga `specs/openapi.yaml` (fuente de verdad) y lo conecta a la app
    ASGI en proceso, con un `base_url` ficticio (nunca se abre un socket
    real: Schemathesis detecta `schema.app` y usa el transporte ASGI)."""
    schema = op.from_path(_OPENAPI_PATH)
    schema.app = app
    schema.config.update(base_url="http://testserver/api/v1")
    return schema


def _seed_synthetic_dataset(database_path: str) -> None:
    """Genera el dataset sintético (mismo wiring que
    `app.main.generar_dataset_inicial_si_vacio`, reimplementado aquí para no
    depender del arranque de `lifespan`, que `TestClient`/el transporte ASGI
    de Schemathesis no ejecutan salvo que se use como context manager)."""
    repo = VisitsRepository(database_path)
    calib = load_model_config()["calibracion"]
    holidays = load_holiday_calendar()
    resultado = generate(
        seed=int(calib["semilla"]),
        years=int(calib["anios"]),
        end_date=ayer_lima(),
        holidays=holidays,
    )
    repo.save_generated(resultado, seed=int(calib["semilla"]))


def _seed_weather_cache(settings: Settings, fixture_payload: dict) -> None:
    """Precarga también la caché de clima (fresca) para que los casos que
    golpean `/clima/actual` no dependan de la latencia/orden de llegada del
    mock de respx -- es un detalle de determinismo, no de aislamiento (respx
    ya garantiza que nunca sale tráfico real)."""
    client = WeatherApiClient(settings)
    conn = sqlite3.connect(settings.database_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS weather_cache ("
            "cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL)"
        )
        fetched_at = datetime.now(UTC).isoformat()
        for cache_key in (client._forecast_cache_key(3), client._current_cache_key()):
            conn.execute(
                "INSERT OR REPLACE INTO weather_cache (cache_key, payload, fetched_at) "
                "VALUES (?, ?, ?)",
                (cache_key, json.dumps(fixture_payload), fetched_at),
            )
        conn.commit()
    finally:
        conn.close()


def test_contrato_openapi_respuestas_reales_cumplen_specs_openapi_yaml(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """QA-03 / specs/08 §1 ("Contrato"): las respuestas reales de los 5
    endpoints cumplen `specs/openapi.yaml` para entradas generadas por
    Hypothesis a partir del propio esquema (formatos, tipos, campos
    requeridos, enums, status codes documentados, content-type).

    Se excluye deliberadamente el check `positive_data_acceptance` de
    Schemathesis: ese check asume que cualquier dato *sintácticamente*
    válido según el esquema (p. ej. `fecha=0001-01-01`, que sólo declara
    `format: date`) debe aceptarse con 2xx. Pero `specs/04-api.md §3`
    documenta una regla de negocio adicional -- `hoy <= fecha <= hoy+2`,
    relativa al reloj del servidor -- que OpenAPI 3.1 no puede expresar de
    forma estática (no existe forma de decir "== hoy" en JSON Schema). El
    422 resultante para esas fechas SÍ está documentado como respuesta
    válida de la operación en `specs/openapi.yaml` (`responses: "422"`), así
    que rechazarlas no es una divergencia real entre el código y el
    contrato: es una limitación conocida de ese check concreto frente a
    validaciones dependientes del reloj. Se mantienen activos todos los
    demás checks por defecto de Schemathesis (`not_a_server_error`,
    `status_code_conformance`, `content_type_conformance`,
    `response_schema_conformance`, `response_headers_conformance`,
    `negative_data_rejection`, ...), que sí verifican fielmente que las
    respuestas reales cumplen el esquema -- si alguno de ellos falla, es un
    defecto real a reportar, no algo que este test silencie.
    """
    db_path = str(tmp_path_factory.mktemp("contract") / "cueva-contract.db")
    _seed_synthetic_dataset(db_path)

    settings = Settings(
        weatherapi_key="test-key-do-not-use",
        database_path=db_path,
        weather_cache_ttl_seconds=1800,
    )
    fixture_ok = _load_fixture("forecast_ok.json")
    _seed_weather_cache(settings, fixture_ok)

    app.dependency_overrides[get_settings] = lambda: settings
    schema = _build_schema()
    failures: list[str] = []

    try:
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FORECAST_URL).mock(return_value=httpx.Response(200, json=fixture_ok))
            mock.get(_CURRENT_URL).mock(return_value=httpx.Response(200, json=fixture_ok))

            strategy = schema.as_strategy()

            @hyp_settings(
                max_examples=_MAX_EXAMPLES,
                deadline=None,
                derandomize=True,
                suppress_health_check=list(HealthCheck),
            )
            @given(case=strategy)
            def _run(case) -> None:
                try:
                    case.call_and_validate(
                        excluded_checks=[openapi_checks.positive_data_acceptance]
                    )
                except Exception as exc:  # noqa: BLE001 -- se agrega a un reporte único
                    failures.append(f"{case.method} {case.formatted_path}\n{exc}")

            _run()
    finally:
        app.dependency_overrides.clear()

    assert not failures, (
        "Divergencias de contrato entre la API y specs/openapi.yaml "
        f"({len(failures)} caso(s)):\n\n" + "\n\n---\n\n".join(failures)
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
