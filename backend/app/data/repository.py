"""Repositorio SQLite del histórico de visitas (specs/02-decision-datos.md §4.4, §5 ADR-02).

Toda la capa de datos accede a SQLite exclusivamente a través de
`VisitsRepository`: ni `app/data/generator.py` ni los routers futuros (BE-06)
tocan `sqlite3` directamente. Esto es lo que permite, según ADR-02, migrar de
SQLite a otro motor (p. ej. RDS PostgreSQL) sin tocar el resto de la
aplicación. Todas las consultas son parametrizadas (P5 de
specs/00-constitucion.md); nunca se concatena SQL con datos externos.

Interfaz pública (contrato para BE-05/BE-06, sin tests que la fijen todavía):

- ``VisitsRepository(database_path)``
- ``create_schema() -> None`` — crea las 3 tablas con ``CREATE TABLE IF NOT
  EXISTS`` (idempotente).
- ``is_empty() -> bool`` — True si ``daily_visits`` no tiene filas (también
  garantiza que el esquema exista).
- ``save_generated(result: GeneratorResult, *, seed: int) -> None`` —
  reemplaza el contenido de ``daily_visits`` con ``result.rows`` y persiste
  ``base_diaria``, ``semilla``, ``generado_en`` (timestamp ISO 8601 UTC) y
  ``version_modelo`` (leído de ``config/model.yaml``) en ``model_params``.
- ``get_model_param(key: str) -> str | None`` — valor crudo de un parámetro.
- ``get_base_diaria() -> float | None`` — atajo tipado sobre
  ``get_model_param("base_diaria")``, para que el predictor (BE-06) no
  parsee strings.
- ``monthly_history(months: int) -> list[MonthlyVisits]`` — histórico
  agregado por año-mes (suma y promedio de ``visitors``), los últimos
  ``months`` meses con datos, en orden cronológico ascendente. Pensado para
  ``GET /historico/mensual?meses=N`` (BE-06).
- ``percentiles() -> Percentiles`` — P25/P75/P95 de ``daily_visits.visitors``
  (interpolación lineal, método "linear" habitual de numpy/Excel),
  recalculados en cada llamada a partir del dataset vigente. Añadido por
  BE-06 para ``nivel_afluencia`` (specs/03-modelo-prediccion.md §3); es la
  única extensión de esta tarea a este módulo, el resto de la interfaz
  documentada arriba es de BE-04/BE-05 y no se modifica.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.data.generator import GeneratorResult
from app.domain.config_loader import load_model_config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_visits (
    date          TEXT PRIMARY KEY,      -- YYYY-MM-DD (America/Lima)
    visitors      INTEGER NOT NULL CHECK (visitors >= 0),
    precip_mm     REAL    NOT NULL,
    maxtemp_c     REAL    NOT NULL,
    thunderstorm  INTEGER NOT NULL CHECK (thunderstorm IN (0,1)),
    is_holiday    INTEGER NOT NULL CHECK (is_holiday IN (0,1)),
    synthetic     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS model_params (
    -- key: 'base_diaria', 'semilla', 'generado_en' o 'version_modelo'
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_cache (
    cache_key   TEXT PRIMARY KEY,         -- 'forecast:<q>:<dias>'
    payload     TEXT NOT NULL,            -- JSON crudo de WeatherAPI
    fetched_at  TEXT NOT NULL             -- ISO 8601 UTC
);
"""

# Claves reconocidas de `model_params` (specs/02 §4.4). No es una tabla de
# lookup en SQLite (la tabla acepta cualquier `key`): documenta el contrato
# que `save_generated` escribe y que BE-06 leerá con `get_model_param`.
MODEL_PARAM_BASE_DIARIA = "base_diaria"
MODEL_PARAM_SEMILLA = "semilla"
MODEL_PARAM_GENERADO_EN = "generado_en"
MODEL_PARAM_VERSION_MODELO = "version_modelo"


@dataclass(frozen=True)
class MonthlyVisits:
    """Histórico agregado de un mes calendario, para `/historico/mensual`."""

    year_month: str  # 'YYYY-MM'
    total_visitors: int
    avg_visitors: float
    days: int


@dataclass(frozen=True)
class Percentiles:
    """P25/P75/P95 de `daily_visits.visitors`, para `nivel_afluencia`
    (specs/03-modelo-prediccion.md §3)."""

    p25: float
    p75: float
    p95: float


def _percentile(valores_ordenados: list[int], pct: float) -> float:
    """Percentil `pct` (0-100) por interpolación lineal entre los dos valores
    de rango más cercanos (método "linear", el mismo que usan por defecto
    numpy/Excel). `valores_ordenados` debe venir ya ordenado ascendentemente
    y no vacío."""
    n = len(valores_ordenados)
    if n == 1:
        return float(valores_ordenados[0])
    rank = (pct / 100) * (n - 1)
    inferior = int(rank)
    superior = min(inferior + 1, n - 1)
    peso = rank - inferior
    valor_inferior = valores_ordenados[inferior]
    valor_superior = valores_ordenados[superior]
    return valor_inferior + (valor_superior - valor_inferior) * peso


class VisitsRepository:
    """Acceso a SQLite para el histórico de visitas y los parámetros del modelo."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._database_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_schema(self) -> None:
        """Crea las tablas si no existen (idempotente, seguro de llamar en
        cada arranque)."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def is_empty(self) -> bool:
        """True si `daily_visits` no tiene ninguna fila. Garantiza que el
        esquema exista antes de consultarlo (seguro de llamar antes de que
        `create_schema()` se haya invocado explícitamente, p. ej. al
        arrancar la app)."""
        self.create_schema()
        with self._connect() as conn:
            fila = conn.execute("SELECT 1 FROM daily_visits LIMIT 1").fetchone()
        return fila is None

    def save_generated(self, result: GeneratorResult, *, seed: int) -> None:
        """Reemplaza `daily_visits` con `result.rows` y persiste
        `base_diaria`/`semilla`/`generado_en`/`version_modelo` en
        `model_params` (specs/02 §4.2, §4.4, RF-07)."""
        self.create_schema()
        version_modelo = load_model_config()["version_modelo"]
        generado_en = datetime.now(UTC).isoformat()

        with self._connect() as conn:
            conn.execute("DELETE FROM daily_visits")
            conn.executemany(
                """
                INSERT INTO daily_visits
                    (date, visitors, precip_mm, maxtemp_c, thunderstorm, is_holiday, synthetic)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.date.isoformat(),
                        row.visitors,
                        row.precip_mm,
                        row.maxtemp_c,
                        int(row.thunderstorm),
                        int(row.is_holiday),
                        int(row.synthetic),
                    )
                    for row in result.rows
                ],
            )
            conn.executemany(
                "INSERT OR REPLACE INTO model_params (key, value) VALUES (?, ?)",
                [
                    (MODEL_PARAM_BASE_DIARIA, str(result.base_diaria)),
                    (MODEL_PARAM_SEMILLA, str(seed)),
                    (MODEL_PARAM_GENERADO_EN, generado_en),
                    (MODEL_PARAM_VERSION_MODELO, str(version_modelo)),
                ],
            )

    def get_model_param(self, key: str) -> str | None:
        """Valor crudo (`TEXT`) de un parámetro de `model_params`, o `None`
        si no existe."""
        with self._connect() as conn:
            fila = conn.execute(
                "SELECT value FROM model_params WHERE key = ?", (key,)
            ).fetchone()
        return fila[0] if fila is not None else None

    def get_base_diaria(self) -> float | None:
        """Atajo tipado sobre `get_model_param('base_diaria')` para el
        predictor (BE-06)."""
        valor = self.get_model_param(MODEL_PARAM_BASE_DIARIA)
        return float(valor) if valor is not None else None

    def monthly_history(self, months: int) -> list[MonthlyVisits]:
        """Histórico agregado por año-mes (`strftime('%Y-%m', date)`), los
        últimos `months` meses con datos en `daily_visits`, ordenados
        cronológicamente ascendente. Usado por `GET
        /historico/mensual?meses=N` (BE-06)."""
        with self._connect() as conn:
            filas = conn.execute(
                """
                SELECT strftime('%Y-%m', date) AS year_month,
                       SUM(visitors)           AS total_visitors,
                       AVG(visitors)           AS avg_visitors,
                       COUNT(*)                AS dias
                FROM daily_visits
                GROUP BY year_month
                ORDER BY year_month DESC
                LIMIT ?
                """,
                (months,),
            ).fetchall()

        resultado = [
            MonthlyVisits(
                year_month=fila[0],
                total_visitors=int(fila[1]),
                avg_visitors=float(fila[2]),
                days=int(fila[3]),
            )
            for fila in filas
        ]
        resultado.reverse()  # cronológico ascendente
        return resultado

    def percentiles(self) -> Percentiles:
        """P25/P75/P95 de `daily_visits.visitors` (specs/03 §3), recalculados
        a partir del dataset vigente en cada llamada. Devuelve todo en 0.0 si
        `daily_visits` está vacía (no debería ocurrir en producción: el
        arranque de `app.main` genera el dataset sintético antes de aceptar
        tráfico, RF-07)."""
        with self._connect() as conn:
            filas = conn.execute("SELECT visitors FROM daily_visits ORDER BY visitors").fetchall()
        valores = [fila[0] for fila in filas]
        if not valores:
            return Percentiles(0.0, 0.0, 0.0)
        return Percentiles(
            p25=_percentile(valores, 25),
            p75=_percentile(valores, 75),
            p95=_percentile(valores, 95),
        )
