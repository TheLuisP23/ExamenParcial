"""Combina los factores en una predicción completa (specs/03 §1, §3, §4).

Cubre RF-02..04 (fórmula, rango, desglose transparente) y RF-11
(advertencias). Módulo de dominio puro: no llama a WeatherAPI ni a SQLite,
no lee la fecha del sistema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.config_loader import load_model_config
from app.domain.factors import (
    ClimaInput,
    Factor,
    es_condicion_tormenta,
    f_clima,
    f_dia_semana,
    f_feriado,
    f_temporada,
)
from app.domain.holidays import HolidayCalendar
from app.domain.rounding import round_half_up

_CFG = load_model_config()
# Los defaults del parametro reflejan config/model.yaml (P7: no son numeros
# magicos independientes, se leen una vez al importar el modulo), pero
# conservan exactamente la firma `capacidad_diaria: float = 1500`,
# `rango_factor_min: float = 0.80`, `rango_factor_max: float = 1.20` que
# especifica el contrato de QA (docstring de tests/unit/test_predictor.py).
_CAPACIDAD_DIARIA_DEFAULT: float = float(_CFG["capacidad_diaria"])
_RANGO_FACTOR_MIN_DEFAULT: float = float(_CFG["rango"]["factor_min"])
_RANGO_FACTOR_MAX_DEFAULT: float = float(_CFG["rango"]["factor_max"])


@dataclass(frozen=True)
class Desglose:
    """Desglose transparente de la predicción (P3: nada de "caja negra")."""

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
    advertencias: list[str]


def _advertencias(clima: ClimaInput | None, cfg: dict) -> list[str]:
    """RF-11 (specs/03 §4). `ALERTA_OFICIAL` depende de `alerts.alert` de
    WeatherAPI, que no forma parte de `ClimaInput`: la genera la capa que sí
    tiene el payload crudo (cliente WeatherAPI / router), no este modulo."""
    if clima is None:
        return ["CLIMA_NO_DISPONIBLE"]

    advertencias: list[str] = []
    if clima.precip_mm >= cfg["advertencias"]["lluvia_extrema_mm"]:
        advertencias.append("LLUVIA_EXTREMA")
    if es_condicion_tormenta(clima):
        advertencias.append("TORMENTA")
    return advertencias


def predict(
    fecha: date,
    clima: ClimaInput | None,
    base_diaria: float,
    holidays: HolidayCalendar,
    *,
    capacidad_diaria: float = _CAPACIDAD_DIARIA_DEFAULT,
    rango_factor_min: float = _RANGO_FACTOR_MIN_DEFAULT,
    rango_factor_max: float = _RANGO_FACTOR_MAX_DEFAULT,
) -> Prediction:
    """specs/03-modelo-prediccion.md §1:

    estimado = min(capacidad_diaria, ROUND_HALF_UP(base_diaria x factores))
    rango_min/max se calculan sobre el `estimado` YA topado.
    """
    es_feriado = holidays.es_feriado(fecha)
    temporada = f_temporada(fecha)
    dia_semana = f_dia_semana(fecha, es_feriado)
    feriado = f_feriado(fecha, holidays)
    clima_factor = f_clima(clima)

    bruto = (
        base_diaria
        * temporada.valor
        * dia_semana.valor
        * feriado.valor
        * clima_factor.valor
    )
    estimado_sin_tope = round_half_up(bruto)
    estimado = min(int(capacidad_diaria), estimado_sin_tope)
    tope_aplicado = estimado_sin_tope > capacidad_diaria

    rango_min = round_half_up(estimado * rango_factor_min)
    rango_max = min(int(capacidad_diaria), round_half_up(estimado * rango_factor_max))

    desglose = Desglose(
        base_diaria=base_diaria,
        temporada=temporada,
        dia_semana=dia_semana,
        feriado=feriado,
        clima=clima_factor,
        tope_capacidad_aplicado=tope_aplicado,
    )
    return Prediction(
        fecha=fecha,
        visitantes_estimados=estimado,
        rango_min=rango_min,
        rango_max=rango_max,
        factores=desglose,
        advertencias=_advertencias(clima, _CFG),
    )


def nivel_afluencia(estimado: int, p25: float, p75: float, p95: float) -> str:
    """specs/03 §3. Límites inclusivos hacia abajo."""
    if estimado <= p25:
        return "Baja"
    if estimado <= p75:
        return "Media"
    if estimado <= p95:
        return "Alta"
    return "Muy alta"
