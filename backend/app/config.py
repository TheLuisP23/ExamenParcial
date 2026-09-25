"""Configuración de la aplicación (specs/04-api.md §5).

Lee variables de entorno (y, si existe, un archivo .env en el cwd) mediante
pydantic-settings. No lee `config/*.yaml`: esos coeficientes/feriados/coordenadas
los cargan los módulos de dominio en tareas posteriores (BE-02+), nunca aquí.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno documentadas en specs/04-api.md §5."""

    weatherapi_key: str
    app_version: str = "dev"
    database_path: str = "./cueva.db"
    weather_cache_ttl_seconds: int = 1800
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Punto único de acceso a `Settings`, apto para `Depends`."""
    return Settings()
