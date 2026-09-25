"""Router de `GET /api/v1/health` (RF-09, HU-05).

No debe llamar a WeatherAPI ni a ninguna dependencia externa: solo confirma
que el proceso está vivo y reporta la versión desplegada.
"""

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.schemas import Health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
def get_health(settings: Settings = Depends(get_settings)) -> Health:
    return Health(status="ok", version=settings.app_version)
