"""Calendario de feriados y detección de "feriado largo" (specs/03 §2.3).

Módulo de dominio puro. `HolidayCalendar` se puede instanciar directamente
con datos ad-hoc (como hacen los tests unitarios) o construirse desde
`config/holidays_pe.yaml` con `load_holiday_calendar()`, que es lo que usará
el wiring de producción (routers, tarea BE-06).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.domain.config_loader import load_holidays_config, load_model_config
from app.domain.factors import Factor

_NOMBRE_JUEVES_SANTO = "Jueves Santo"
_NOMBRE_VIERNES_SANTO = "Viernes Santo"


def _pascua(anio: int) -> date:
    """Domingo de Pascua gregoriano (algoritmo de Meeus/Jones/Butcher).

    Se implementa en Python puro (sin `python-dateutil`, que no es una
    dependencia del proyecto) porque `config/holidays_pe.yaml` requiere
    calcular Jueves y Viernes Santo cada año. Verificado para 2026:
    Pascua=2026-04-05 (domingo) (ver `test_UT_22_...` en
    `tests/unit/test_holidays.py`).
    """
    a = anio % 19
    b = anio // 100
    c = anio % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    mes = (h + ell - 7 * m + 114) // 31
    dia = ((h + ell - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def _jueves_santo(anio: int) -> date:
    return _pascua(anio) - timedelta(days=3)


def _viernes_santo(anio: int) -> date:
    return _pascua(anio) - timedelta(days=2)


@dataclass(frozen=True)
class HolidayCalendar:
    """Calendario de feriados peruanos usado por `f_feriado` (specs/03 §2.3).

    fijos: "MM-DD" -> nombre del feriado (se repite cada año).
    no_laborables: "YYYY" -> lista de "YYYY-MM-DD" (decretos anuales del
        Ejecutivo; se tratan como feriado para el modelo).
    semana_santa: si True, detecta Jueves y Viernes Santo del año de la
        fecha consultada mediante el cómputo de la Pascua.
    """

    fijos: dict[str, str]
    no_laborables: dict[str, list[str]] = field(default_factory=dict)
    semana_santa: bool = True

    def _semana_santa_nombre(self, fecha: date) -> str | None:
        if not self.semana_santa:
            return None
        if fecha == _jueves_santo(fecha.year):
            return _NOMBRE_JUEVES_SANTO
        if fecha == _viernes_santo(fecha.year):
            return _NOMBRE_VIERNES_SANTO
        return None

    def nombre(self, fecha: date) -> str | None:
        nombre_fijo = self.fijos.get(fecha.strftime("%m-%d"))
        if nombre_fijo is not None:
            return nombre_fijo

        fechas_decreto = self.no_laborables.get(str(fecha.year), [])
        if fecha.isoformat() in fechas_decreto:
            return "Día no laborable (decreto)"

        return self._semana_santa_nombre(fecha)

    def es_feriado(self, fecha: date) -> bool:
        return self.nombre(fecha) is not None

    def _es_no_laborable(self, fecha: date) -> bool:
        return fecha.weekday() >= 5 or self.es_feriado(fecha)

    def es_bloque_largo(self, fecha: date) -> bool:
        """True si `fecha` pertenece a un bloque >= `min_dias_bloque_largo`
        de días consecutivos no laborables (fin de semana y/o feriados)."""
        if not self._es_no_laborable(fecha):
            return False

        inicio = fecha
        while self._es_no_laborable(inicio - timedelta(days=1)):
            inicio -= timedelta(days=1)

        fin = fecha
        while self._es_no_laborable(fin + timedelta(days=1)):
            fin += timedelta(days=1)

        min_dias = load_model_config()["feriado"]["min_dias_bloque_largo"]
        return (fin - inicio).days + 1 >= min_dias

    def factor(self, fecha: date) -> Factor:
        """== `f_feriado(fecha, self)`. specs/03 §2.3: el bloque largo (1.60)
        tiene prioridad sobre el feriado aislado (1.35)."""
        cfg = load_model_config()["feriado"]

        if self.es_bloque_largo(fecha):
            nombre = self.nombre(fecha)
            if nombre:
                razon = f"Feriado largo ({nombre})"
            else:
                razon = "Feriado largo (fin de semana extendido)"
            return Factor(cfg["largo"], razon)

        nombre = self.nombre(fecha)
        if nombre is not None:
            return Factor(cfg["aislado"], f"Feriado: {nombre}")

        return Factor(cfg["normal"], "Día normal")


def load_holiday_calendar() -> HolidayCalendar:
    """Construye el `HolidayCalendar` de producción desde
    `config/holidays_pe.yaml` (usado por el wiring de routers, BE-06)."""
    data = load_holidays_config()
    return HolidayCalendar(
        fijos=data.get("fijos") or {},
        no_laborables=data.get("no_laborables") or {},
        semana_santa=bool(data.get("semana_santa", True)),
    )
