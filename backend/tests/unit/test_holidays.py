"""Tests unitarios de feriados y feriados largos (UT-20..23, RF-02).

TDD deliberado: ver el docstring superior de `test_predictor.py` para el
contrato completo de `app/domain/holidays.py` y `app/domain/factors.py`
asumido por QA. Fallos por `ModuleNotFoundError`/`ImportError` son el
resultado esperado mientras `app/domain/` no exista (tareas BE-02/BE-03).

Resumen del contrato usado aqui:

    class HolidayCalendar:
        def __init__(
            self,
            fijos: dict[str, str],                    # "MM-DD" -> nombre
            no_laborables: dict[str, list[str]] | None = None,  # "YYYY" -> ["YYYY-MM-DD"]
            semana_santa: bool = True,                 # detecta Jueves/Viernes Santo
        ): ...
        def es_feriado(self, fecha: date) -> bool: ...
        def es_bloque_largo(self, fecha: date) -> bool: ...
        def factor(self, fecha: date) -> Factor: ...   # == f_feriado(fecha, self)

    def f_dia_semana(fecha: date, es_feriado: bool) -> Factor

Fechas de Jueves y Viernes Santo 2026 verificadas con el algoritmo de
Meeus/Jones/Butcher para la Pascua gregoriana (independiente de la
implementacion de dominio): Pascua 2026-04-05 (domingo) => Viernes Santo
2026-04-03, Jueves Santo 2026-04-02.
"""

from datetime import date

from app.domain.factors import f_dia_semana
from app.domain.holidays import HolidayCalendar


def test_UT_20_navidad_es_feriado_largo_viernes_sabado_domingo() -> None:
    """2026-12-25 (viernes) y 2026-12-26 (sabado) son parte del bloque
    vie-sab-dom => factor_feriado = 1.60 en ambos dias."""
    calendar = HolidayCalendar(fijos={"12-25": "Navidad"})

    viernes = calendar.factor(date(2026, 12, 25))
    sabado = calendar.factor(date(2026, 12, 26))
    domingo = calendar.factor(date(2026, 12, 27))

    assert calendar.es_bloque_largo(date(2026, 12, 25)) is True
    assert calendar.es_bloque_largo(date(2026, 12, 26)) is True
    assert calendar.es_bloque_largo(date(2026, 12, 27)) is True
    assert viernes.valor == 1.60
    assert sabado.valor == 1.60
    assert domingo.valor == 1.60


def test_UT_21_feriado_aislado_en_miercoles() -> None:
    """Un feriado en miercoles sin fin de semana ni otro feriado adyacente
    es 'aislado' => factor 1.35 (specs/03 §2.3)."""
    # 2026-06-03 es miercoles; 2026-06-02 (martes) y 2026-06-04 (jueves) no
    # son feriados ni fin de semana, asi que el bloque no laborable tiene
    # longitud 1.
    calendar = HolidayCalendar(fijos={"06-03": "Feriado de prueba (aislado)"})
    fecha = date(2026, 6, 3)
    assert fecha.weekday() == 2  # miercoles

    factor = calendar.factor(fecha)

    assert calendar.es_bloque_largo(fecha) is False
    assert factor.valor == 1.35


def test_UT_22_jueves_y_viernes_santo_son_feriado_largo() -> None:
    """Jueves Santo (2026-04-02) y Viernes Santo (2026-04-03) se detectan
    automaticamente (semana_santa=True) y forman un bloque largo junto con
    el fin de semana de Pascua (sabado 04-04, domingo 04-05)."""
    calendar = HolidayCalendar(fijos={}, semana_santa=True)
    jueves_santo = date(2026, 4, 2)
    viernes_santo = date(2026, 4, 3)

    assert calendar.es_feriado(jueves_santo) is True
    assert calendar.es_feriado(viernes_santo) is True
    assert calendar.es_bloque_largo(jueves_santo) is True
    assert calendar.es_bloque_largo(viernes_santo) is True
    assert calendar.factor(jueves_santo).valor == 1.60
    assert calendar.factor(viernes_santo).valor == 1.60


def test_UT_23_domingo_normal_no_es_feriado() -> None:
    """Un domingo sin feriados alrededor: factor_feriado=1.00 y
    f_dia_semana=1.50 (specs/03 §2.2 y §2.3)."""
    # Semana santa desactivada y sin fijos para aislar el caso de un
    # domingo "normal" que no coincide con ningun feriado.
    calendar = HolidayCalendar(fijos={}, semana_santa=False)
    domingo = date(2026, 9, 27)
    assert domingo.weekday() == 6  # domingo

    assert calendar.es_feriado(domingo) is False
    assert calendar.factor(domingo).valor == 1.00

    factor_dia = f_dia_semana(domingo, es_feriado=calendar.es_feriado(domingo))
    assert factor_dia.valor == 1.50
