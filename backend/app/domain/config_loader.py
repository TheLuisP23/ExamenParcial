"""Carga de `config/*.yaml` para el dominio (specs/00-constitucion.md P7).

`app/domain/` es puro (sin FastAPI, sin SQLite, sin llamadas de red), pero sí
necesita leer los coeficientes del modelo y los feriados desde `config/` en
vez de tenerlos como números mágicos incrustados en el código (P7). Este
módulo resuelve la ruta al directorio `config/` (hermano de `backend/` en la
raíz del repositorio) y expone loaders cacheados (`functools.lru_cache`, los
YAML no cambian durante la vida del proceso) para `model.yaml` y
`holidays_pe.yaml`.

La búsqueda del directorio `config/` sube desde este archivo por sus
directorios padre hasta encontrar uno que contenga `model.yaml`, lo que
funciona tanto para `pytest` ejecutado dentro de `backend/` como para
cualquier otro cwd dentro del checkout. `CONFIG_DIR` permite forzar la ruta
(por ejemplo, si en el futuro la imagen Docker copia `config/` a otra
ubicación; ver nota en el reporte de la tarea BE-02/BE-03 sobre el Dockerfile
actual).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _find_config_dir() -> Path:
    override = os.environ.get("CONFIG_DIR")
    if override:
        candidate = Path(override)
        if (candidate / "model.yaml").is_file():
            return candidate

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config"
        if (candidate / "model.yaml").is_file():
            return candidate

    raise FileNotFoundError(
        "No se encontro config/model.yaml. Defina la variable de entorno "
        "CONFIG_DIR apuntando al directorio config/, o ejecute desde un "
        "checkout completo del repositorio (config/ hermano de backend/)."
    )


def _load_yaml(filename: str) -> dict[str, Any]:
    path = _find_config_dir() / filename
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def load_model_config() -> dict[str, Any]:
    """Carga y cachea `config/model.yaml` (specs/03-modelo-prediccion.md)."""
    return _load_yaml("model.yaml")


@lru_cache
def load_holidays_config() -> dict[str, Any]:
    """Carga y cachea `config/holidays_pe.yaml` (specs/03 §2.3)."""
    return _load_yaml("holidays_pe.yaml")
