"""Reloj de la aplicación (specs/04-api.md §4, specs/02-decision-datos.md §4).

Los módulos de dominio (`app.domain.*`) y el generador (`app.data.generator`)
son puros: nunca leen la fecha del sistema, siempre la reciben inyectada
(specs/03-modelo-prediccion.md §1). Este módulo es el único punto de la capa
de infraestructura donde se lee el reloj real, en la zona horaria de la
cueva (America/Lima, UTC-5, sin horario de verano). Lo usa el wiring de
arranque de `app.main` (RF-07) y lo reutilizarán tareas futuras (BE-06,
`/predicciones`) para obtener "hoy".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

LIMA_TZ = ZoneInfo("America/Lima")


def hoy_lima() -> date:
    """Fecha actual en America/Lima."""
    return datetime.now(LIMA_TZ).date()


def ayer_lima() -> date:
    """Día inmediatamente anterior a `hoy_lima()`.

    Es el "día inclusive más reciente" que se considera cerrado/observable
    para el histórico sintético, y por tanto el `end_date` que se inyecta en
    `app.data.generator.generate()` en producción (specs/02 §4.2: "para cada
    día d en [hoy - años, ayer]").
    """
    return hoy_lima() - timedelta(days=1)
