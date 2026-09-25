"""Factores puros del modelo `reglas-v1` (specs/03-modelo-prediccion.md §2).

Módulo de dominio: sin FastAPI, sin SQLite, sin llamadas HTTP. El único I/O
es la lectura (cacheada) de `config/model.yaml` vía `config_loader` (P7). Las
funciones no leen la fecha del sistema: `fecha` siempre llega como
parámetro, inyectada por un `Clock` en capas superiores (specs/04-api.md §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from app.domain.config_loader import load_model_config

if TYPE_CHECKING:
    # Solo para tipado: `factors.py` nunca importa `holidays` en tiempo de
    # ejecución (evita el ciclo holidays -> factors -> holidays, ya que
    # holidays.py sí importa `Factor` de este módulo).
    from app.domain.holidays import HolidayCalendar

_MESES = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]

_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


@dataclass(frozen=True)
class Factor:
    """Multiplicador adimensional (specs/00-constitucion.md §5) con su razón."""

    valor: float
    razon: str


@dataclass(frozen=True)
class HourlyPoint:
    """Un punto horario de `WeatherAPI` (`forecastday[].hour[]`)."""

    hour: int
    chance_of_rain: int
    condition_code: int | None = None


@dataclass(frozen=True)
class ClimaInput:
    """Entrada de clima normalizada para un día (`forecastday[].day`)."""

    precip_mm: float
    maxtemp_c: float
    chance_of_rain: int | None = None
    condition_code: int | None = None
    hourly: list[HourlyPoint] | None = None


def f_temporada(fecha: date) -> Factor:
    """specs/03 §2.1: factor por mes."""
    valor = load_model_config()["temporada"][fecha.month]
    return Factor(valor, f"{_MESES[fecha.month - 1]}: factor de temporada")


def f_dia_semana(fecha: date, es_feriado: bool) -> Factor:
    """specs/03 §2.2. Si `es_feriado`, usa el valor de sábado salvo domingo."""
    cfg = load_model_config()["dia_semana"]
    if es_feriado and fecha.weekday() != 6:
        return Factor(cfg[5], "Feriado (tratado como sábado)")
    dow = fecha.weekday()
    return Factor(cfg[dow], _DIAS[dow])


def f_feriado(fecha: date, holidays: HolidayCalendar) -> Factor:
    """specs/03 §2.3. Delega en `HolidayCalendar.factor`, que es la misma regla."""
    return holidays.factor(fecha)


def es_condicion_tormenta(clima: ClimaInput) -> bool:
    """True si el código de condición del día, o de alguna hora 08-17h, indica
    tormenta eléctrica (specs/03 §2.4). La ventana 08-17h es el "Horario de
    visita" fijo de specs/00-constitucion.md §5 (no un coeficiente afinable),
    por eso no está en `config/model.yaml`.
    """
    codigos = set(load_model_config()["clima"]["tormenta"]["codigos"])
    if clima.condition_code in codigos:
        return True
    if clima.hourly:
        return any(
            8 <= p.hour < 17 and p.condition_code in codigos for p in clima.hourly
        )
    return False


def _f_lluvia(precip_mm: float, tramos: list[list[float]]) -> float:
    # `tramos` viene ordenado ascendentemente por `desde` en config/model.yaml;
    # se usa el ultimo tramo cuyo `desde` <= precip_mm (specs/03 §2.4).
    valor = tramos[0][1]
    for desde, factor in tramos:
        if precip_mm >= desde:
            valor = factor
    return valor


def _f_horario(hourly: list[HourlyPoint] | None, cfg: dict[str, Any]) -> float:
    if not hourly:
        return 1.00
    desde, hasta = cfg["desde"], cfg["hasta"]
    chance_minima = cfg["chance_minima"]
    horas_calificando = sum(
        1
        for p in hourly
        if desde <= p.hour < hasta and p.chance_of_rain >= chance_minima
    )
    return cfg["factor"] if horas_calificando >= cfg["horas_minimas"] else 1.00


def _f_tormenta(clima: ClimaInput, cfg: dict[str, Any]) -> float:
    return cfg["factor"] if es_condicion_tormenta(clima) else 1.00


def _f_calor(maxtemp_c: float, cfg: dict[str, Any]) -> float:
    return cfg["factor"] if maxtemp_c >= cfg["maxtemp_c"] else 1.00


def _f_dia_seco(clima: ClimaInput, cfg: dict[str, Any]) -> float:
    if clima.precip_mm >= cfg["precip_max_mm"]:
        return 1.00
    # `chance_of_rain=None` (generador sintetico): solo aplica precip_mm.
    if clima.chance_of_rain is not None and clima.chance_of_rain >= cfg["chance_max"]:
        return 1.00
    return cfg["factor"]


def f_clima(clima: ClimaInput | None) -> Factor:
    """specs/03 §2.4. `clima=None` (RF-06) => factor neutro 1.00."""
    if clima is None:
        return Factor(1.00, "Clima no disponible")

    cfg = load_model_config()["clima"]
    lluvia = _f_lluvia(clima.precip_mm, cfg["lluvia_tramos"])
    horario = _f_horario(clima.hourly, cfg["horario"])
    tormenta = _f_tormenta(clima, cfg["tormenta"])
    calor = _f_calor(clima.maxtemp_c, cfg["calor"])
    dia_seco = _f_dia_seco(clima, cfg["dia_seco"])

    valor = max(cfg["piso"], lluvia * horario * tormenta * calor * dia_seco)
    razon = f"Lluvia {clima.precip_mm:.1f} mm"
    return Factor(valor, razon)
