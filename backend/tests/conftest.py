"""Configuración compartida de tests.

`WEATHERAPI_KEY` es obligatoria en `app.config.Settings` (specs/04-api.md §5),
así que se fija un valor ficticio antes de que cualquier test module importe
`app.main`/`app.config`. Nunca se llama a la WeatherAPI real en los tests.
"""

import os

os.environ.setdefault("WEATHERAPI_KEY", "test-key-do-not-use")
