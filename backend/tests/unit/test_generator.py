"""Tests unitarios del generador de dataset sintetico (UT-30..35 = CA-GEN-1..6,
specs/02-decision-datos.md §4.5, RF-07).

TDD deliberado: `app/data/generator.py` todavia no existe (pendiente de
BE-04). Fallos por `ModuleNotFoundError`/`ImportError` son el resultado
esperado hasta esa tarea.

=====================================================================
CONTRATO DE DOMINIO ASUMIDO POR QA (specs/02 §4, specs/04-api.md §4)
=====================================================================

``app/data/generator.py``
    @dataclass(frozen=True)
    class DailyRow:
        date: date
        visitors: int
        precip_mm: float
        maxtemp_c: float
        thunderstorm: bool
        is_holiday: bool
        synthetic: bool = True    # columna `synthetic` de `daily_visits` (1/0 en SQLite)

    @dataclass(frozen=True)
    class GeneratorResult:
        rows: list[DailyRow]
        base_diaria: float        # se persiste en `model_params['base_diaria']`

    def generate(
        *,
        seed: int,
        years: int,
        end_date: date,            # dia inclusive mas reciente generado
                                    # ("ayer" en produccion; se inyecta en los
                                    # tests para que el generador sea puro y
                                    # no dependa del reloj del sistema, igual
                                    # que el predictor -- specs/03 §1).
        visitantes_anuales_parque: int = 160_000,
        proporcion_cueva: float = 0.80,
        ruido_sigma: float = 0.15,
        capacidad_diaria: int = 1500,
        holidays: "HolidayCalendar",
    ) -> GeneratorResult
        # Algoritmo exacto: specs/02-decision-datos.md §4.2. `generate` debe
        # ser determinista: misma `seed` + mismos demas parametros =>
        # exactamente las mismas filas (CA-GEN-1). Usa las MISMAS funciones
        # de factores que `app.domain.predictor` (f_temporada, f_dia_semana,
        # f_feriado, f_clima) para que historico y prediccion sean coherentes.
=====================================================================
"""

from collections import Counter
from datetime import date

import pytest
from app.data.generator import generate
from app.domain.holidays import HolidayCalendar

CAPACIDAD_DIARIA = 1500
CALENDAR = HolidayCalendar(fijos={"12-25": "Navidad"})


def _generate(*, seed: int = 42, years: int = 3, end_date: date = date(2026, 12, 31)):
    return generate(
        seed=seed,
        years=years,
        end_date=end_date,
        capacidad_diaria=CAPACIDAD_DIARIA,
        holidays=CALENDAR,
    )


@pytest.fixture(scope="module")
def dataset_3_anios():
    """Dataset de 3 anios generado una sola vez (seed=42) y reutilizado por
    CA-GEN-2..6: no hay dependencia de orden porque cada test solo LEE
    `result.rows`, nunca lo muta."""
    return _generate(seed=42, years=3, end_date=date(2026, 12, 31))


def test_UT_30_CA_GEN_1_misma_semilla_produce_filas_identicas() -> None:
    """CA-GEN-1: con semilla=42, dos ejecuciones producen exactamente las
    mismas filas."""
    primera = _generate(seed=42, years=1, end_date=date(2026, 6, 30))
    segunda = _generate(seed=42, years=1, end_date=date(2026, 6, 30))

    assert primera.rows == segunda.rows
    assert primera.base_diaria == pytest.approx(segunda.base_diaria)


def test_UT_31_CA_GEN_2_suma_anual_dentro_de_5_porciento(dataset_3_anios) -> None:
    """CA-GEN-2: la suma de visitantes de cualquier año completo generado
    esta dentro de +/-5% de visitantes_anuales_parque * proporcion_cueva
    (160000 * 0.80 = 128000 con los valores por defecto)."""
    objetivo = 160_000 * 0.80
    conteo_por_anio = Counter(row.date.year for row in dataset_3_anios.rows)
    anio_completo, dias = conteo_por_anio.most_common(1)[0]
    assert dias >= 365, "se esperaba al menos un año calendario completo en el dataset"

    total_anio = sum(
        row.visitors for row in dataset_3_anios.rows if row.date.year == anio_completo
    )

    assert objetivo * 0.95 <= total_anio <= objetivo * 1.05


def test_UT_32_CA_GEN_3_lluvia_extrema_reduce_el_promedio(dataset_3_anios) -> None:
    """CA-GEN-3: promedio de visitantes con precip_mm>=25 < promedio con
    precip_mm<2."""
    lluviosos = [row.visitors for row in dataset_3_anios.rows if row.precip_mm >= 25]
    secos = [row.visitors for row in dataset_3_anios.rows if row.precip_mm < 2]
    assert lluviosos, "no se generaron dias con precip_mm >= 25 para comparar"
    assert secos, "no se generaron dias con precip_mm < 2 para comparar"

    promedio_lluvioso = sum(lluviosos) / len(lluviosos)
    promedio_seco = sum(secos) / len(secos)

    assert promedio_lluvioso < promedio_seco


def test_UT_33_CA_GEN_4_fin_de_semana_supera_martes_miercoles(dataset_3_anios) -> None:
    """CA-GEN-4: promedio de sabados+domingos > promedio de martes+miercoles."""
    fin_de_semana = [row.visitors for row in dataset_3_anios.rows if row.date.weekday() in (5, 6)]
    entre_semana = [row.visitors for row in dataset_3_anios.rows if row.date.weekday() in (1, 2)]
    assert fin_de_semana and entre_semana

    promedio_fin_de_semana = sum(fin_de_semana) / len(fin_de_semana)
    promedio_entre_semana = sum(entre_semana) / len(entre_semana)

    assert promedio_fin_de_semana > promedio_entre_semana


def test_UT_34_CA_GEN_5_sin_negativos_ni_por_encima_de_capacidad(dataset_3_anios) -> None:
    """CA-GEN-5: ningun valor negativo ni por encima de capacidad_diaria."""
    assert all(row.visitors >= 0 for row in dataset_3_anios.rows)
    assert all(row.visitors <= CAPACIDAD_DIARIA for row in dataset_3_anios.rows)


def test_UT_35_CA_GEN_6_todas_las_filas_son_sinteticas(dataset_3_anios) -> None:
    """CA-GEN-6: todas las filas tienen synthetic=1 (True)."""
    assert all(row.synthetic for row in dataset_3_anios.rows)
    assert all(bool(row.synthetic) is True for row in dataset_3_anios.rows)
