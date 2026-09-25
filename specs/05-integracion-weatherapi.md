# 05 · Integración con WeatherAPI.com

## 1. Plan y límites (plan Free)

| Límite | Valor | Impacto en el diseño |
|--------|-------|----------------------|
| Llamadas | 100 000 / mes | Caché de 30 min → como máximo ~1 440 llamadas/mes por endpoint. |
| Pronóstico | 3 días | La app solo predice hoy, hoy+1, hoy+2 (RF-05). |
| Histórico | 1 día hacia atrás | No sirve para construir histórico → dataset sintético (ADR-01). |
| Atribución | Se pide enlazar a WeatherAPI.com | RF-10. |

> Verificar los límites vigentes en https://www.weatherapi.com/pricing.aspx antes de la entrega.

## 2. Llamadas que hace el backend

**Pronóstico (para `/predicciones`):**

```
GET https://api.weatherapi.com/v1/forecast.json
    ?key=${WEATHERAPI_KEY}
    &q=-9.3292,-76.0269
    &days=3
    &aqi=no
    &alerts=yes
    &lang=es
```

**Actual (para `/clima/actual`):**

```
GET https://api.weatherapi.com/v1/current.json?key=${WEATHERAPI_KEY}&q=-9.3292,-76.0269&aqi=no&lang=es
```

- Se usa **HTTPS** y **coordenadas** (no "Tingo Maria"), porque el nombre puede resolverse al centro de la ciudad y la cueva está a ~7 km.
- Las coordenadas viven en `config/location.yaml`.

## 3. Mapeo de campos

| Campo WeatherAPI | Uso interno |
|------------------|-------------|
| `forecast.forecastday[].date` | `fecha` |
| `…day.totalprecip_mm` | `f_lluvia`, `f_dia_seco`, advertencia `LLUVIA_EXTREMA` |
| `…day.daily_chance_of_rain` | `f_dia_seco`, `clima.probabilidad_lluvia` |
| `…day.maxtemp_c` / `mintemp_c` | `f_calor`, `clima.temp_max_c` / `temp_min_c` |
| `…day.condition.{text,code,icon}` | `f_tormenta`, `clima.condicion`, `clima.icono_url` (anteponer `https:`) |
| `…hour[].time`, `chance_of_rain`, `condition.code` | `f_horario`, `f_tormenta` (solo horas 08–17) |
| `alerts.alert[].headline` | advertencia `ALERTA_OFICIAL` |
| `location.localtime` | informativo |

## 4. Resiliencia

| Aspecto | Regla |
|---------|-------|
| Timeout | 5 s total por llamada. |
| Reintentos | 2 reintentos con backoff (0.5 s, 1 s) solo ante timeout o HTTP 5xx. Nunca ante 4xx. |
| Caché | Tabla `weather_cache`, TTL `WEATHER_CACHE_TTL_SECONDS` (1 800 s). Si la API falla y hay caché **de hasta 6 h**, se usa la caché y se registra un warning. |
| Degradación | Sin API y sin caché válida → `/predicciones` con `f_clima=1.0` (RF-06); `/clima/actual` → 503. |
| Logs | Nunca registrar la URL completa (contiene la llave). Registrar solo `endpoint`, `status`, `duración_ms`. |

## 5. Errores de WeatherAPI a manejar

| Código WeatherAPI | HTTP | Significado | Acción |
|-------------------|------|-------------|--------|
| 1002 | 401 | Falta la llave | Log ERROR, degradar. |
| 1006 | 400 | Ubicación no encontrada | Log ERROR (config incorrecta), degradar. |
| 2006 | 401 | Llave inválida | Log ERROR, degradar. |
| 2007 | 403 | Cuota mensual excedida | Log ERROR, degradar, usar caché. |
| 2008 | 403 | Llave deshabilitada | Log ERROR, degradar. |
| 9999 | 400 | Error interno de WeatherAPI | Reintentar según §4. |

## 6. Fixtures para pruebas

El agente QA debe guardar respuestas reales **anonimizadas** (sin la llave) en
`backend/tests/fixtures/weatherapi/`:

- `forecast_ok.json` — respuesta real de 3 días.
- `forecast_lluvia_extrema.json` — editada: día 1 con `totalprecip_mm = 55` y código 1276.
- `forecast_alerta.json` — con un elemento en `alerts.alert`.
- `error_2006.json`, `error_2007.json`.

Ningún test de CI llama a la WeatherAPI real (se usa `respx`). Solo el smoke test post-deploy la ejercita indirectamente.
