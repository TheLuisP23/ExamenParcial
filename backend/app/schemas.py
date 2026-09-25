"""Modelos Pydantic = contrato OpenAPI (specs/openapi.yaml).

BE-01 definió el esquema de `/health`. Esta tarea (BE-06) añade los esquemas
de `/predicciones`, `/clima/actual`, `/historico/mensual` y `/modelo`,
espejando `specs/openapi.yaml` campo por campo (P3: transparencia del
modelo; nombres en español tal cual el contrato, no traducidos ni
renombrados).
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    """Respuesta de `GET /api/v1/health` (componente `Health` de openapi.yaml)."""

    status: Literal["ok"]
    version: str


class ErrorDetalle(BaseModel):
    codigo: Literal[
        "FECHA_INVALIDA",
        "FECHA_FUERA_DE_RANGO",
        "PARAMETRO_INVALIDO",
        "CLIMA_NO_DISPONIBLE",
        "ERROR_INTERNO",
    ]
    mensaje: str


class ErrorResponse(BaseModel):
    """Formato único de error (specs/04-api.md §3, componente `Error` de openapi.yaml)."""

    error: ErrorDetalle


# --------------------------------------------------------------------------
# `GET /predicciones` (componentes `Factor`, `Factores`, `ClimaDia`,
# `Advertencia`, `Prediccion`, `PrediccionesResponse` de openapi.yaml).
# --------------------------------------------------------------------------


class Factor(BaseModel):
    """Componente `Factor`: multiplicador adimensional con su razón (P3)."""

    valor: float = Field(ge=0, le=2)
    razon: str


class Factores(BaseModel):
    """Componente `Factores`: desglose transparente de la predicción (P3)."""

    base_diaria: float
    temporada: Factor
    dia_semana: Factor
    feriado: Factor
    clima: Factor
    tope_capacidad_aplicado: bool


class ClimaDia(BaseModel):
    """Componente `ClimaDia`."""

    condicion: str
    codigo_condicion: int
    icono_url: str | None = None
    temp_max_c: float
    temp_min_c: float
    precipitacion_mm: float = Field(ge=0)
    probabilidad_lluvia: int = Field(ge=0, le=100)


class Advertencia(BaseModel):
    """Componente `Advertencia` (RF-11, specs/03 §4)."""

    codigo: Literal["LLUVIA_EXTREMA", "TORMENTA", "ALERTA_OFICIAL", "CLIMA_NO_DISPONIBLE"]
    mensaje: str


class Rango(BaseModel):
    """Sub-objeto `rango` de `Prediccion` (`{min, max}` en openapi.yaml)."""

    min: int = Field(ge=0)
    max: int = Field(ge=0)


class Prediccion(BaseModel):
    """Componente `Prediccion`."""

    fecha: date
    visitantes_estimados: int = Field(ge=0, le=1500)
    rango: Rango
    nivel_afluencia: Literal["Baja", "Media", "Alta", "Muy alta"]
    clima_disponible: bool
    clima: ClimaDia | None = None
    factores: Factores
    advertencias: list[Advertencia]


class Ubicacion(BaseModel):
    """Sub-objeto `ubicacion` de `PrediccionesResponse` (`config/location.yaml`)."""

    nombre: str
    lat: float
    lon: float


class PrediccionesResponse(BaseModel):
    """Componente `PrediccionesResponse`."""

    ubicacion: Ubicacion
    version_modelo: str
    datos_sinteticos: Literal[True]
    generado_en: datetime
    predicciones: list[Prediccion] = Field(min_length=1, max_length=3)
    atribucion: Literal["Powered by WeatherAPI.com"]


# --------------------------------------------------------------------------
# `GET /clima/actual` (componente `ClimaActual`).
# --------------------------------------------------------------------------


class ClimaActual(BaseModel):
    """Componente `ClimaActual`."""

    temp_c: float
    sensacion_c: float | None = None
    condicion: str
    icono_url: str | None = None
    humedad: int
    precipitacion_mm: float | None = None
    actualizado_en: datetime


# --------------------------------------------------------------------------
# `GET /historico/mensual` (componente `HistoricoMensual`).
# --------------------------------------------------------------------------


class SerieMensual(BaseModel):
    """Elemento de `HistoricoMensual.serie`."""

    mes: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    visitantes: int
    promedio_diario: float


class HistoricoMensual(BaseModel):
    """Componente `HistoricoMensual`."""

    datos_sinteticos: Literal[True]
    serie: list[SerieMensual]


# --------------------------------------------------------------------------
# `GET /modelo` (componente `Modelo`).
# --------------------------------------------------------------------------


class Modelo(BaseModel):
    """Componente `Modelo` (P3: transparencia del modelo)."""

    version_modelo: str
    base_diaria: float
    capacidad_diaria: int
    coeficientes: dict
