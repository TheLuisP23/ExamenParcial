# 04 · Contrato de la API REST

> El contrato formal está en [`openapi.yaml`](./openapi.yaml). Este documento lo explica.
> **Regla:** si el código y `openapi.yaml` difieren, el código está mal.

Base: `/api/v1` · Formato: JSON UTF-8 · Sin autenticación (solo lectura, datos públicos).

## 1. Endpoints

| Método | Ruta | Descripción | RF |
|--------|------|-------------|----|
| GET | `/api/v1/health` | Estado y versión desplegada. No llama a WeatherAPI. | RF-09 |
| GET | `/api/v1/predicciones` | Predicción para hoy, mañana y pasado mañana. | RF-01..05, RF-11 |
| GET | `/api/v1/predicciones?fecha=YYYY-MM-DD` | Predicción de un solo día (hoy ≤ fecha ≤ hoy+2). | RF-05 |
| GET | `/api/v1/clima/actual` | Clima actual en la cueva. | RF-01 |
| GET | `/api/v1/historico/mensual?meses=36` | Visitantes sintéticos agregados por mes (1 ≤ meses ≤ 36). | RF-08 |
| GET | `/api/v1/modelo` | Versión y coeficientes vigentes del modelo. | P3 |
| GET | `/docs` | Swagger UI generado por FastAPI. | — |

## 2. Ejemplo: `GET /api/v1/predicciones?fecha=2026-07-18`

```json
{
  "ubicacion": {
    "nombre": "Cueva de las Lechuzas, PN Tingo María",
    "lat": -9.3292,
    "lon": -76.0269
  },
  "version_modelo": "reglas-v1",
  "datos_sinteticos": true,
  "generado_en": "2026-07-17T20:15:03-05:00",
  "predicciones": [
    {
      "fecha": "2026-07-18",
      "visitantes_estimados": 426,
      "rango": { "min": 341, "max": 511 },
      "nivel_afluencia": "Alta",
      "clima_disponible": true,
      "clima": {
        "condicion": "Lluvia moderada",
        "codigo_condicion": 1189,
        "icono_url": "https://cdn.weatherapi.com/weather/64x64/day/302.png",
        "temp_max_c": 29.0,
        "temp_min_c": 21.4,
        "precipitacion_mm": 12.0,
        "probabilidad_lluvia": 60
      },
      "factores": {
        "base_diaria": 350,
        "temporada": { "valor": 1.20, "razon": "Julio: vacaciones de medio año" },
        "dia_semana": { "valor": 1.45, "razon": "Sábado" },
        "feriado":    { "valor": 1.00, "razon": "Día normal" },
        "clima":      { "valor": 0.70, "razon": "Lluvia 12.0 mm (10–25 mm)" },
        "tope_capacidad_aplicado": false
      },
      "advertencias": []
    }
  ],
  "atribucion": "Powered by WeatherAPI.com"
}
```

## 3. Errores

Formato único para todos los errores:

```json
{ "error": { "codigo": "FECHA_FUERA_DE_RANGO", "mensaje": "La fecha debe estar entre 2026-09-25 y 2026-09-27." } }
```

| HTTP | `codigo` | Cuándo |
|------|----------|--------|
| 422 | `FECHA_INVALIDA` | `fecha` no es `YYYY-MM-DD` válido. |
| 422 | `FECHA_FUERA_DE_RANGO` | `fecha` < hoy o > hoy+2 (America/Lima). |
| 422 | `PARAMETRO_INVALIDO` | `meses` fuera de 1..36. |
| 503 | `CLIMA_NO_DISPONIBLE` | Solo en `/clima/actual` cuando WeatherAPI falla y no hay caché. |
| 500 | `ERROR_INTERNO` | Cualquier excepción no controlada (sin stack trace en la respuesta). |

> `/predicciones` **nunca** devuelve 503 por WeatherAPI: degrada con `clima_disponible=false` (RF-06).

## 4. Implementación (FastAPI)

```
backend/
├── app/
│   ├── main.py              # crea la app, monta routers, CORS, handlers de error
│   ├── config.py            # Settings (pydantic-settings) desde env + config/*.yaml
│   ├── api/v1/              # routers: health, predictions, weather, history, model
│   ├── domain/
│   │   ├── factors.py       # funciones puras f_temporada, f_dia_semana, f_feriado, f_clima
│   │   ├── predictor.py     # combina factores → Prediction
│   │   └── holidays.py      # calendario y detección de feriado largo
│   ├── clients/weatherapi.py# cliente httpx + caché + reintentos
│   ├── data/
│   │   ├── generator.py     # dataset sintético (CLI)
│   │   └── repository.py    # VisitsRepository (SQLite)
│   └── schemas.py           # modelos Pydantic = contrato OpenAPI
├── tests/
├── Dockerfile
└── pyproject.toml
```

- `domain/` **no importa** nada de `api/`, `clients/` ni `data/` (dominio puro, fácil de testear).
- La fecha "hoy" se obtiene de un `Clock` inyectable (`zoneinfo.ZoneInfo("America/Lima")`) para que los tests fijen la fecha.
- CORS: solo el mismo origen en producción (Nginx sirve front y API en el mismo host).

## 5. Variables de entorno

| Variable | Obligatoria | Ejemplo | Descripción |
|----------|-------------|---------|-------------|
| `WEATHERAPI_KEY` | Sí | `abc123…` | Llave de WeatherAPI.com. **Secreto.** |
| `APP_VERSION` | No | `a1b2c3d` | SHA corto; la inyecta el pipeline. Default `dev`. |
| `DATABASE_PATH` | No | `/data/cueva.db` | Ruta del SQLite. |
| `WEATHER_CACHE_TTL_SECONDS` | No | `1800` | TTL de caché del pronóstico. |
| `LOG_LEVEL` | No | `INFO` | |
