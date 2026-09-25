"""Router de `GET /api/v1/modelo` (P3: transparencia del modelo, specs/04-api.md §1).

`base_diaria` viene del dataset sintético vigente (`VisitsRepository`,
recalculado en cada generación); `version_modelo`/`capacidad_diaria`/
`coeficientes` vienen de `config/model.yaml` (P7: configuración, no
constantes).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_repository
from app.data.repository import VisitsRepository
from app.domain.config_loader import load_model_config
from app.schemas import Modelo

router = APIRouter(tags=["modelo"])

# Claves de `config/model.yaml` que ya se exponen como campos propios de
# `Modelo` (`version_modelo`, `capacidad_diaria`): el resto del YAML (
# `calibracion`, `rango`, `temporada`, `dia_semana`, `feriado`, `clima`,
# `advertencias`) se expone tal cual en `coeficientes` (P3: nada de "caja
# negra"; `additionalProperties: true` en el contrato da libertad para esto).
_CAMPOS_PROPIOS = {"version_modelo", "capacidad_diaria"}


@router.get("/modelo", response_model=Modelo)
def get_modelo(repo: VisitsRepository = Depends(get_repository)) -> Modelo:
    cfg = load_model_config()
    return Modelo(
        version_modelo=str(cfg["version_modelo"]),
        base_diaria=repo.get_base_diaria() or 0.0,
        capacidad_diaria=int(cfg["capacidad_diaria"]),
        coeficientes={k: v for k, v in cfg.items() if k not in _CAMPOS_PROPIOS},
    )
