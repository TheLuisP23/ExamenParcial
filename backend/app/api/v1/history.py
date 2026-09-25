"""Router de `GET /api/v1/historico/mensual` (RF-08, specs/04-api.md §1-3).

Validación manual de `meses` (specs/04-api.md §3): se declara sin `ge`/`le`
de Pydantic para poder devolver el formato de error `{error: {codigo,
mensaje}}` del contrato (`PARAMETRO_INVALIDO`) en vez del 422 genérico de
FastAPI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.deps import get_repository
from app.data.repository import VisitsRepository
from app.schemas import HistoricoMensual, SerieMensual

router = APIRouter(tags=["historico"])

_MESES_MIN = 1
_MESES_MAX = 36


def _error_parametro_invalido(mensaje: str) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"codigo": "PARAMETRO_INVALIDO", "mensaje": mensaje}},
    )


@router.get("/historico/mensual", response_model=HistoricoMensual)
def get_historico_mensual(
    meses: int | str = Query(36, description="1..36, default 36."),
    repo: VisitsRepository = Depends(get_repository),
) -> HistoricoMensual | JSONResponse:
    """RF-08: visitantes sintéticos agregados por mes, últimos `meses` meses
    con datos (1 <= meses <= 36)."""
    try:
        meses_int = int(meses)
    except (TypeError, ValueError):
        return _error_parametro_invalido(
            f"'meses' debe ser un entero entre {_MESES_MIN} y {_MESES_MAX}."
        )

    if not (_MESES_MIN <= meses_int <= _MESES_MAX):
        return _error_parametro_invalido(
            f"'meses' debe estar entre {_MESES_MIN} y {_MESES_MAX}."
        )

    historico = repo.monthly_history(meses_int)
    serie = [
        SerieMensual(
            mes=mes.year_month,
            visitantes=mes.total_visitors,
            promedio_diario=round(mes.avg_visitors, 2),
        )
        for mes in historico
    ]
    return HistoricoMensual(datos_sinteticos=True, serie=serie)
