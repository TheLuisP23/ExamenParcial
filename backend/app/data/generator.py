"""Generador del dataset sintético de visitas (RF-07, specs/02-decision-datos.md §4).

Módulo de la capa de datos (`app/data/`): a diferencia de `app.domain`, aquí
sí hay "I/O" en el sentido amplio (lectura de `config/climate_synthetic.yaml`
y consumo de un generador de números pseudoaleatorios), pero `generate()` en
sí misma sigue siendo pura respecto del reloj del sistema: `end_date` llega
siempre inyectada (nunca se lee `date.today()` aquí), igual que exige
specs/03-modelo-prediccion.md §1 para el resto del dominio.

Reutiliza las MISMAS funciones de factores que `app.domain.predictor`
(`f_temporada`, `f_dia_semana`, `f_feriado`, `f_clima`) para que histórico y
predicción sean coherentes (specs/02 §4.2), y `app.domain.rounding.round_half_up`
para el redondeo final, por consistencia con el resto del dominio.
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.domain.config_loader import load_model_config
from app.domain.factors import ClimaInput, f_clima, f_dia_semana, f_feriado, f_temporada
from app.domain.holidays import HolidayCalendar, load_holiday_calendar
from app.domain.rounding import round_half_up

# Defaults de calibración (P7: se leen de config/model.yaml, no son números
# mágicos independientes del resto del dominio; coinciden con los valores
# publicados en specs/02 §4.1 y con los que fija el contrato de QA en
# tests/unit/test_generator.py).
_CFG = load_model_config()
_CALIB = _CFG["calibracion"]
VISITANTES_ANUALES_PARQUE_DEFAULT: int = int(_CALIB["visitantes_anuales_parque"])
PROPORCION_CUEVA_DEFAULT: float = float(_CALIB["proporcion_cueva"])
SEMILLA_DEFAULT: int = int(_CALIB["semilla"])
ANIOS_DEFAULT: int = int(_CALIB["anios"])
RUIDO_SIGMA_DEFAULT: float = float(_CALIB["ruido_sigma"])
CAPACIDAD_DIARIA_DEFAULT: int = int(_CFG["capacidad_diaria"])


def _find_climate_config_dir() -> Path:
    """Localiza el directorio `config/` (hermano de `backend/`) igual que
    `app.domain.config_loader._find_config_dir`, pero resuelto aquí de forma
    independiente para no importar un símbolo privado de `app.domain` (que
    no debe tocarse ni acoplarse a necesidades nuevas de la capa de datos).
    """
    import os

    override = os.environ.get("CONFIG_DIR")
    if override:
        candidate = Path(override)
        if (candidate / "climate_synthetic.yaml").is_file():
            return candidate

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config"
        if (candidate / "climate_synthetic.yaml").is_file():
            return candidate

    raise FileNotFoundError(
        "No se encontró config/climate_synthetic.yaml. Defina la variable de "
        "entorno CONFIG_DIR apuntando al directorio config/, o ejecute desde "
        "un checkout completo del repositorio (config/ hermano de backend/)."
    )


@lru_cache
def _load_climate_synthetic_config() -> dict[str, Any]:
    """Carga y cachea `config/climate_synthetic.yaml` (specs/02 §4.3)."""
    path = _find_climate_config_dir() / "climate_synthetic.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass(frozen=True)
class DailyRow:
    """Una fila sintética de `daily_visits` (specs/02 §4.4)."""

    date: date
    visitors: int
    precip_mm: float
    maxtemp_c: float
    thunderstorm: bool
    is_holiday: bool
    synthetic: bool = True


@dataclass(frozen=True)
class GeneratorResult:
    rows: list[DailyRow]
    base_diaria: float  # se persiste en `model_params['base_diaria']`


def _rango_fechas(end_date: date, years: int) -> date:
    """`end_date` - `years` años + 1 día (specs/02 §4.2: "[hoy - años, ayer]",
    aquí con `end_date` ya inyectado en lugar de "ayer" literal)."""
    try:
        inicio_del_ultimo_anio = end_date.replace(year=end_date.year - years)
    except ValueError:
        # end_date es 29 de febrero y `end_date.year - years` no es bisiesto.
        inicio_del_ultimo_anio = end_date.replace(year=end_date.year - years, day=28)
    return inicio_del_ultimo_anio + timedelta(days=1)


def _codigo_tormenta_sintetico() -> int:
    """Un código cualquiera de `config/model.yaml → clima.tormenta.codigos`
    (el primero) para que `f_clima`/`es_condicion_tormenta` reconozcan la
    tormenta sintética con la misma lógica que en producción."""
    return int(_CFG["clima"]["tormenta"]["codigos"][0])


def _muestrear_clima(rng: random.Random, mes: int) -> tuple[ClimaInput, bool]:
    """Muestrea el clima sintético de un día de mes `mes` (specs/02 §4.3).

    Orden fijo de consumo de `rng` (parte de por qué `generate()` es
    determinista para una `seed` dada, CA-GEN-1): lluvia sí/no -> monto de
    lluvia (solo si llovió) -> temperatura máxima -> tormenta.
    """
    cfg_mes = _load_climate_synthetic_config()["meses"][mes]

    llueve = rng.random() < cfg_mes["p_lluvia"]
    if llueve:
        precip_mm = rng.gammavariate(alpha=1.5, beta=cfg_mes["mm_medio"] / 1.5)
    else:
        precip_mm = 0.0

    maxtemp_c = rng.gauss(cfg_mes["tmax"], 1.5)

    tormenta = rng.random() < cfg_mes["p_tormenta"]
    condition_code = _codigo_tormenta_sintetico() if tormenta else None

    clima = ClimaInput(
        precip_mm=precip_mm,
        maxtemp_c=maxtemp_c,
        chance_of_rain=None,
        condition_code=condition_code,
        hourly=None,
    )
    return clima, tormenta


def generate(
    *,
    seed: int,
    years: int,
    end_date: date,
    visitantes_anuales_parque: int = VISITANTES_ANUALES_PARQUE_DEFAULT,
    proporcion_cueva: float = PROPORCION_CUEVA_DEFAULT,
    ruido_sigma: float = RUIDO_SIGMA_DEFAULT,
    capacidad_diaria: int = CAPACIDAD_DIARIA_DEFAULT,
    holidays: HolidayCalendar,
) -> GeneratorResult:
    """Genera el histórico sintético diario (specs/02 §4.2, RF-07).

    Determinista (CA-GEN-1): toda la aleatoriedad se consume desde una única
    instancia `random.Random(seed)`, recorriendo los días en orden
    cronológico ascendente y muestreando siempre en el mismo orden por día
    (ver `_muestrear_clima`), de modo que dos llamadas con la misma `seed` y
    los mismos demás parámetros producen exactamente las mismas filas.

    `end_date` es el día inclusive más reciente generado ("ayer" en
    producción; se inyecta siempre para que esta función sea pura y no lea
    el reloj del sistema, igual que `app.domain.predictor.predict`).
    """
    rng = random.Random(seed)
    inicio = _rango_fechas(end_date, years)

    fechas: list[date] = []
    climas: list[ClimaInput] = []
    tormentas: list[bool] = []
    es_feriados: list[bool] = []
    brutos: list[float] = []

    dia = inicio
    while dia <= end_date:
        clima, tormenta = _muestrear_clima(rng, dia.month)
        ruido = rng.gauss(0.0, ruido_sigma)

        es_feriado = holidays.es_feriado(dia)
        f = (
            f_temporada(dia).valor
            * f_dia_semana(dia, es_feriado).valor
            * f_feriado(dia, holidays).valor
            * f_clima(clima).valor
        )
        bruto = f * math.exp(ruido)

        fechas.append(dia)
        climas.append(clima)
        tormentas.append(tormenta)
        es_feriados.append(es_feriado)
        brutos.append(bruto)

        dia += timedelta(days=1)

    suma_bruto = sum(brutos)
    base_diaria = (visitantes_anuales_parque * proporcion_cueva * years) / suma_bruto

    rows = [
        DailyRow(
            date=fecha,
            visitors=min(capacidad_diaria, round_half_up(base_diaria * bruto)),
            precip_mm=clima.precip_mm,
            maxtemp_c=clima.maxtemp_c,
            thunderstorm=tormenta,
            is_holiday=es_feriado,
            synthetic=True,
        )
        for fecha, clima, tormenta, es_feriado, bruto in zip(
            fechas, climas, tormentas, es_feriados, brutos, strict=True
        )
    ]
    return GeneratorResult(rows=rows, base_diaria=base_diaria)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.data.generator",
        description="Genera y persiste el dataset sintético de visitas (RF-07).",
    )
    parser.add_argument("--seed", type=int, default=SEMILLA_DEFAULT, help="Semilla del RNG.")
    parser.add_argument(
        "--years", type=int, default=ANIOS_DEFAULT, help="Años de histórico a generar."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI: `python -m app.data.generator --seed 42 --years 3` (specs/02 §4).

    Genera con `end_date` = ayer en America/Lima y persiste vía
    `VisitsRepository` en `Settings.database_path`. Importa `app.clock`,
    `app.config` y `app.data.repository` de forma perezosa (dentro de la
    función) para que `import app.data.generator` -- usado por los tests
    unitarios puros de `generate()` -- no dependa de que `WEATHERAPI_KEY`
    esté configurada.
    """
    from app.clock import ayer_lima
    from app.config import get_settings
    from app.data.repository import VisitsRepository

    args = _parse_args(argv)
    holidays = load_holiday_calendar()
    resultado = generate(
        seed=args.seed,
        years=args.years,
        end_date=ayer_lima(),
        holidays=holidays,
    )

    settings = get_settings()
    repo = VisitsRepository(settings.database_path)
    repo.save_generated(resultado, seed=args.seed)

    print(
        f"Dataset sintético generado: {len(resultado.rows)} filas "
        f"(seed={args.seed}, years={args.years}), "
        f"base_diaria={resultado.base_diaria:.4f}"
    )


if __name__ == "__main__":
    main()
