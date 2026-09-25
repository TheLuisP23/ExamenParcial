"""Dependencias FastAPI compartidas entre routers de `api/v1` (BE-06).

No forma parte del contrato OpenAPI: solo evita repetir en cada router
(`predictions.py`, `history.py`, `model.py`) el wiring de `VisitsRepository`
a partir de `Settings.database_path`.
"""

from fastapi import Depends

from app.config import Settings, get_settings
from app.data.repository import VisitsRepository


def get_repository(settings: Settings = Depends(get_settings)) -> VisitsRepository:
    """Factoría para `Depends(get_repository)`: una `VisitsRepository` sobre
    `Settings.database_path`."""
    return VisitsRepository(settings.database_path)
