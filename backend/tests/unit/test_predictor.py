"""Tests unitarios del modelo `reglas-v1` (UT-01..13, RF-02, RF-03, RF-04).

TDD deliberado (specs/00-constitucion.md P1, specs/08-plan-pruebas.md §2.1):
`app/domain/` todavia no existe (tarea BE-01 completada, BE-02/BE-03
pendientes). Es normal y esperado que este modulo falle por
`ModuleNotFoundError`/`ImportError` hasta que el agente `back` implemente
los archivos de dominio. Estas pruebas SON el contrato que debe cumplir esa
implementacion.

=====================================================================
CONTRATO DE DOMINIO ASUMIDO POR QA (specs/04-api.md §4, specs/03 y specs/05)
=====================================================================

``app/domain/rounding.py``
    def round_half_up(x: float) -> int
        Redondeo comercial (mitad hacia arriba), a diferencia de `round()`
        nativo de Python que usa "banker's rounding" (redondeo al par mas
        cercano). specs/03-modelo-prediccion.md §1 exige ROUND_HALF_UP.

``app/domain/factors.py``
    @dataclass(frozen=True)
    class Factor:
        valor: float
        razon: str          # texto humano, ver ejemplo specs/04-api.md §2

    @dataclass(frozen=True)
    class HourlyPoint:
        hour: int                    # 0-23, hora local de inicio del bloque
        chance_of_rain: int          # 0-100, WeatherAPI `hour[].chance_of_rain`
        condition_code: int | None = None   # WeatherAPI `hour[].condition.code`

    @dataclass(frozen=True)
    class ClimaInput:
        precip_mm: float             # `day.totalprecip_mm`
        maxtemp_c: float             # `day.maxtemp_c`
        chance_of_rain: int | None = None   # `day.daily_chance_of_rain`;
                                             # None solo en el generador
                                             # sintetico (no aplica el
                                             # criterio de chance en f_dia_seco,
                                             # solo precip_mm < 1 -- specs/03 §2.4)
        condition_code: int | None = None   # `day.condition.code`
        hourly: list[HourlyPoint] | None = None  # `hour[]`; None => sin datos
                                                  # horarios (generador
                                                  # sintetico), f_horario = 1.00

    def f_temporada(fecha: date) -> Factor
    def f_dia_semana(fecha: date, es_feriado: bool) -> Factor
        # `es_feriado=True` fuerza el valor de sabado (1.45), salvo que
        # `fecha.weekday() == 6` (domingo), que conserva 1.50
        # (specs/03-modelo-prediccion.md §2.2).
    def f_feriado(fecha: date, holidays: "HolidayCalendar") -> Factor
    def f_clima(clima: ClimaInput | None) -> Factor
        # clima=None => Factor(1.00, "Clima no disponible") (RF-06).
        # Ventana de f_horario: horas con 8 <= hour < 16 (media abierta:
        # el bloque horario 15:00-16:00, hour=15, SI cuenta; hour=16 y
        # hour=7 NO cuentan). >=4 horas con chance_of_rain >= 70 => 0.85.

``app/domain/holidays.py``
    @dataclass(frozen=True)
    class HolidayCalendar:
        fijos: dict[str, str]                       # "MM-DD" -> nombre
        no_laborables: dict[str, list[str]] = {}     # "YYYY" -> ["YYYY-MM-DD", ...]
        semana_santa: bool = True                    # detecta Jueves/Viernes
                                                       # Santo del anio de `fecha`

        def es_feriado(self, fecha: date) -> bool
        def nombre(self, fecha: date) -> str | None
        def es_bloque_largo(self, fecha: date) -> bool
            # True si `fecha` pertenece a un bloque de >=3 dias NO
            # laborables consecutivos (fin de semana sabado/domingo +
            # feriados, incluyendo Jueves/Viernes Santo).
        def factor(self, fecha: date) -> Factor   # == f_feriado(fecha, self)

``app/domain/predictor.py``
    @dataclass(frozen=True)
    class Desglose:
        base_diaria: float
        temporada: Factor
        dia_semana: Factor
        feriado: Factor
        clima: Factor
        tope_capacidad_aplicado: bool

    @dataclass(frozen=True)
    class Prediction:
        fecha: date
        visitantes_estimados: int
        rango_min: int
        rango_max: int
        factores: Desglose
        advertencias: list[str]     # codigos RF-11, p.ej. ["LLUVIA_EXTREMA"]

    def predict(
        fecha: date,
        clima: ClimaInput | None,
        base_diaria: float,
        holidays: HolidayCalendar,
        *,
        capacidad_diaria: float = 1500,
        rango_factor_min: float = 0.80,
        rango_factor_max: float = 1.20,
    ) -> Prediction
        # estimado = min(capacidad_diaria, round_half_up(base_diaria * prod(factores)))
        # rango_min/max se calculan sobre el `estimado` YA topado
        # (specs/03-modelo-prediccion.md §1).

    def nivel_afluencia(estimado: int, p25: float, p75: float, p95: float) -> str
        # "Baja" | "Media" | "Alta" | "Muy alta" (specs/03 §3, limites
        # inclusivos hacia abajo: Baja <= P25, Media <= P75, Alta <= P95).
=====================================================================
"""

from dataclasses import dataclass
from datetime import date

import pytest
from app.domain.factors import ClimaInput, HourlyPoint, f_clima
from app.domain.holidays import HolidayCalendar
from app.domain.predictor import nivel_afluencia, predict
from app.domain.rounding import round_half_up

# HolidayCalendar compartido por la tabla dorada: solo Navidad es relevante
# (T4/T6 usan 2026-12-25, feriado largo vie-sab-dom). Las demas fechas de la
# tabla no son feriados.
HOLIDAYS = HolidayCalendar(fijos={"12-25": "Navidad"})


@dataclass(frozen=True)
class GoldenCase:
    id: str
    fecha: date
    clima: ClimaInput | None
    base_diaria: float
    temporada: float
    dia_semana: float
    feriado: float
    clima_factor: float
    estimado: int
    rango_min: int
    rango_max: int
    tope: bool = False


GOLDEN_TABLE = [
    GoldenCase(
        id="T1",
        fecha=date(2026, 7, 18),  # sabado
        clima=ClimaInput(precip_mm=12, chance_of_rain=60, maxtemp_c=29.0),
        base_diaria=350,
        temporada=1.20,
        dia_semana=1.45,
        feriado=1.00,
        clima_factor=0.70,
        estimado=426,
        rango_min=341,
        rango_max=511,
    ),
    GoldenCase(
        id="T2",
        fecha=date(2026, 3, 10),  # martes
        clima=ClimaInput(precip_mm=0.5, chance_of_rain=10, maxtemp_c=28.0),
        base_diaria=350,
        temporada=0.90,
        dia_semana=0.70,
        feriado=1.00,
        clima_factor=1.05,
        estimado=232,
        rango_min=186,
        rango_max=278,
    ),
    GoldenCase(
        id="T3",
        fecha=date(2026, 10, 18),  # domingo
        clima=ClimaInput(
            precip_mm=55, chance_of_rain=85, maxtemp_c=27.0, condition_code=1276
        ),
        base_diaria=350,
        temporada=0.90,
        dia_semana=1.50,
        feriado=1.00,
        clima_factor=0.30,  # max(0.30, 0.35*0.80)
        estimado=142,
        rango_min=114,
        rango_max=170,
    ),
    GoldenCase(
        id="T4",
        fecha=date(2026, 12, 25),  # viernes, feriado largo vie-sab-dom
        clima=ClimaInput(precip_mm=1.5, chance_of_rain=40, maxtemp_c=30.0),
        base_diaria=350,
        temporada=1.05,
        dia_semana=1.45,  # feriado -> valor de sabado
        feriado=1.60,
        clima_factor=1.00,
        estimado=853,
        rango_min=682,
        rango_max=1024,
    ),
    GoldenCase(
        id="T5",
        fecha=date(2026, 7, 18),  # sabado, WeatherAPI caido
        clima=None,
        base_diaria=350,
        temporada=1.20,
        dia_semana=1.45,
        feriado=1.00,
        clima_factor=1.00,
        estimado=609,
        rango_min=487,
        rango_max=731,
    ),
    GoldenCase(
        id="T6",
        fecha=date(2026, 12, 25),  # viernes, feriado largo, base_diaria=700
        clima=ClimaInput(precip_mm=0, chance_of_rain=5, maxtemp_c=30.0),
        base_diaria=700,
        temporada=1.05,
        dia_semana=1.45,
        feriado=1.60,
        clima_factor=1.05,
        estimado=1500,  # tope de capacidad (bruto = 1790.46)
        rango_min=1200,
        rango_max=1500,
        tope=True,
    ),
    GoldenCase(
        id="T7",
        fecha=date(2026, 5, 12),  # martes
        clima=ClimaInput(
            precip_mm=8,
            chance_of_rain=75,
            maxtemp_c=35.0,
            hourly=[HourlyPoint(hour=h, chance_of_rain=75) for h in range(8, 13)],
        ),
        base_diaria=350,
        temporada=0.95,
        dia_semana=0.70,
        feriado=1.00,
        clima_factor=0.6885,
        estimado=160,
        rango_min=128,
        rango_max=192,
    ),
]


@pytest.mark.parametrize("caso", GOLDEN_TABLE, ids=[c.id for c in GOLDEN_TABLE])
def test_UT_01_07_tabla_dorada(caso: GoldenCase) -> None:
    """RF-02, RF-03: tabla dorada T1-T7 de specs/03-modelo-prediccion.md §5."""
    prediction = predict(
        fecha=caso.fecha,
        clima=caso.clima,
        base_diaria=caso.base_diaria,
        holidays=HOLIDAYS,
    )

    assert prediction.factores.temporada.valor == pytest.approx(caso.temporada)
    assert prediction.factores.dia_semana.valor == pytest.approx(caso.dia_semana)
    assert prediction.factores.feriado.valor == pytest.approx(caso.feriado)
    assert prediction.factores.clima.valor == pytest.approx(caso.clima_factor, abs=1e-4)
    assert prediction.visitantes_estimados == caso.estimado
    assert prediction.rango_min == caso.rango_min
    assert prediction.rango_max == caso.rango_max
    assert prediction.factores.tope_capacidad_aplicado == caso.tope


@pytest.mark.parametrize(
    "precip_mm,esperado",
    [
        (1.99, 1.00),
        (2.00, 0.90),
        (9.99, 0.90),
        (10.00, 0.70),
        (25.00, 0.50),
        (50.00, 0.35),
    ],
)
def test_UT_08_bordes_de_lluvia(precip_mm: float, esperado: float) -> None:
    """RF-02: bordes de f_lluvia (specs/03 §2.4). Resto de sub-factores neutros:
    precip >= 1.99 nunca activa f_dia_seco, sin tormenta, temp < 34 => f_calor=1.00,
    sin horas => f_horario=1.00. Por lo tanto f_clima == f_lluvia en estos casos.
    """
    clima = ClimaInput(precip_mm=precip_mm, chance_of_rain=50, maxtemp_c=25.0)

    factor = f_clima(clima)

    assert factor.valor == pytest.approx(esperado)


def test_UT_09_f_clima_nunca_baja_de_0_30() -> None:
    """RF-02: lluvia 80mm + tormenta + horario + calor simultaneos -> piso 0.30."""
    clima = ClimaInput(
        precip_mm=80,
        chance_of_rain=90,
        maxtemp_c=36.0,
        condition_code=1276,
        hourly=[HourlyPoint(hour=h, chance_of_rain=90) for h in range(8, 12)],
    )

    factor = f_clima(clima)

    assert factor.valor == pytest.approx(0.30)


@pytest.mark.parametrize(
    "horas_qualifying,horas_extra,esperado",
    [
        pytest.param([8, 9, 10], [], 1.00, id="3_horas_no_llega_a_4"),
        pytest.param([8, 9, 10, 11], [], 0.85, id="4_horas_activa_el_factor"),
        pytest.param([8, 9], [7, 16], 1.00, id="horas_fuera_de_08_16_no_cuentan"),
    ],
)
def test_UT_10_f_horario(
    horas_qualifying: list[int], horas_extra: list[int], esperado: float
) -> None:
    """RF-02: f_horario cuenta solo horas con 8 <= hour < 16 y chance_of_rain >= 70.

    precip=1.5 mm (no dispara f_lluvia ni f_dia_seco) y sin tormenta/calor, de modo
    que f_clima == f_horario en este escenario.
    """
    hourly = [HourlyPoint(hour=h, chance_of_rain=95) for h in horas_qualifying]
    hourly += [HourlyPoint(hour=h, chance_of_rain=95) for h in horas_extra]
    clima = ClimaInput(precip_mm=1.5, chance_of_rain=50, maxtemp_c=25.0, hourly=hourly)

    factor = f_clima(clima)

    assert factor.valor == pytest.approx(esperado)


def test_UT_11_round_half_up_difiere_del_round_nativo() -> None:
    """RF-02: ROUND_HALF_UP (specs/03 §1) vs banker's rounding de Python."""
    assert round_half_up(230.5) == 231
    assert round_half_up(232.5) == 233
    # Demuestra la diferencia con el `round()` nativo de Python (redondeo al par):
    assert round(230.5) == 230
    assert round(232.5) == 232
    assert round_half_up(230.5) != round(230.5)
    assert round_half_up(232.5) != round(232.5)


def test_UT_12_desglose_reproduce_el_estimado() -> None:
    """RF-04 (HU-03): base_diaria x factores del desglose reproduce visitantes_estimados."""
    fecha = date(2026, 7, 18)  # sabado, sin feriado, sin tope de capacidad
    clima = ClimaInput(precip_mm=12, chance_of_rain=60, maxtemp_c=29.0)

    prediction = predict(fecha=fecha, clima=clima, base_diaria=350, holidays=HOLIDAYS)

    bruto = (
        prediction.factores.base_diaria
        * prediction.factores.temporada.valor
        * prediction.factores.dia_semana.valor
        * prediction.factores.feriado.valor
        * prediction.factores.clima.valor
    )
    assert round_half_up(bruto) == prediction.visitantes_estimados
    assert prediction.factores.tope_capacidad_aplicado is False


@pytest.mark.parametrize(
    "estimado,esperado",
    [
        pytest.param(220, "Baja", id="en_P25"),
        pytest.param(221, "Media", id="P25_mas_1"),
        pytest.param(415, "Media", id="en_P75"),
        pytest.param(730, "Alta", id="en_P95"),
        pytest.param(731, "Muy alta", id="P95_mas_1"),
    ],
)
def test_UT_13_nivel_afluencia_en_los_limites(estimado: int, esperado: str) -> None:
    """RF-03: nivel de afluencia en P25, P25+1, P75, P95, P95+1 (percentiles inyectados)."""
    nivel = nivel_afluencia(estimado, p25=220, p75=415, p95=730)

    assert nivel == esperado
