# 08 · Plan de pruebas (agente QA)

## 1. Pirámide

| Nivel | Herramienta | Dónde corre | Qué cubre |
|-------|-------------|-------------|-----------|
| Unitarias backend | pytest | CI | Factores, predictor, feriados, generador (dominio puro). |
| Integración backend | pytest + `httpx.AsyncClient` + respx | CI | Endpoints con WeatherAPI simulada y SQLite temporal. |
| Contrato | Schemathesis sobre `specs/openapi.yaml` | CI | Que las respuestas reales cumplan el esquema. |
| Unitarias frontend | Vitest + Testing Library | CI | Componentes y estados (cargando, error, sin clima). |
| E2E | Playwright | CI (contra `docker compose` local con API mock) | Flujo HU-01..HU-04 en navegador. |
| Smoke post-deploy | `curl` + `jq` en `deploy.yml` | GitHub Actions contra EC2 | HU-05, CA-DEP-1, CA-DEP-2. |

Meta de cobertura backend: **≥ 80 %** líneas (bloquea CI). `domain/`: **≥ 95 %**.

## 2. Casos obligatorios

### 2.1 Modelo (`tests/unit/test_predictor.py`)

| ID | Caso | Requisito |
|----|------|-----------|
| UT-01..07 | Tabla dorada T1–T7 de `03-modelo-prediccion.md` §5 (test parametrizado) | RF-02, RF-03 |
| UT-08 | Bordes de lluvia: 1.99 → 1.00; 2.00 → 0.90; 9.99 → 0.90; 10.00 → 0.70; 25.00 → 0.50; 50.00 → 0.35 | RF-02 |
| UT-09 | `f_clima` nunca baja de 0.30 (lluvia 80 mm + tormenta + horario + calor) | RF-02 |
| UT-10 | `f_horario`: 3 horas ≥ 70 % → 1.00; 4 horas → 0.85; horas fuera de 08–16 no cuentan | RF-02 |
| UT-11 | Redondeo `ROUND_HALF_UP`: 230.5 → 231 y 232.5 → 233 (el `round()` de Python daría 230 y 232) | RF-02 |
| UT-12 | `estimado × factores` del desglose reproduce el número (HU-03) | RF-04 |
| UT-13 | Nivel de afluencia en P25, P25+1, P75, P95, P95+1 | RF-03 |

### 2.2 Feriados (`tests/unit/test_holidays.py`)

| ID | Caso |
|----|------|
| UT-20 | 2026-12-25 (vie) es feriado largo (vie–sáb–dom) → 1.60 y sábado 26 también 1.60. |
| UT-21 | Un feriado en miércoles es aislado → 1.35. |
| UT-22 | Jueves y Viernes Santo del año se detectan como feriado largo. |
| UT-23 | Un domingo normal no es feriado → 1.00 y `f_dia_semana = 1.50`. |

### 2.3 Generador (`tests/unit/test_generator.py`)

UT-30..35 = criterios **CA-GEN-1 a CA-GEN-6** de `02-decision-datos.md` §4.5.

### 2.4 API (`tests/integration/`)

| ID | Caso | Esperado |
|----|------|----------|
| IT-01 | `GET /predicciones` con `forecast_ok.json` | 200, 3 elementos, fechas ascendentes, `datos_sinteticos=true`. |
| IT-02 | `?fecha=hoy+3` | 422 `FECHA_FUERA_DE_RANGO`. |
| IT-03 | `?fecha=2026-02-30` | 422 `FECHA_INVALIDA`. |
| IT-04 | WeatherAPI timeout (respx) sin caché | 200, `clima_disponible=false`, `f_clima=1.0`, advertencia `CLIMA_NO_DISPONIBLE`. |
| IT-05 | WeatherAPI caída **con** caché de 2 h | 200, `clima_disponible=true` (usa caché). |
| IT-06 | Dos llamadas seguidas a `/predicciones` | WeatherAPI recibe **1** sola llamada (caché). |
| IT-07 | Error 2007 (cuota) | Degrada; log ERROR sin la llave. |
| IT-08 | `forecast_lluvia_extrema.json` | advertencias `LLUVIA_EXTREMA` y `TORMENTA` en el día 1. |
| IT-09 | `forecast_alerta.json` | advertencia `ALERTA_OFICIAL` con el `headline`. |
| IT-10 | `/health` | 200 `{status: ok, version: APP_VERSION}`; respx verifica 0 llamadas a WeatherAPI. |
| IT-11 | `/historico/mensual?meses=37` | 422 `PARAMETRO_INVALIDO`. |
| IT-12 | Reloj fijado a 2026-09-25 23:30 Lima (= 26 sep 04:30 UTC) | "hoy" es **25 sep**. |
| IT-13 | Ninguna respuesta ni log contiene el valor de `WEATHERAPI_KEY` (buscar el string en `caplog` y cuerpos). | P5 |

### 2.5 Frontend

| ID | Caso |
|----|------|
| FT-01 | Renderiza 3 `TarjetaDia` con datos mock; la primera dice "Hoy". |
| FT-02 | Chip de nivel muestra texto además del color. |
| FT-03 | `clima_disponible=false` → texto "Estimación solo con calendario". |
| FT-04 | 500 en `/predicciones` → mensaje de error y botón Reintentar que vuelve a llamar. |
| FT-05 | El pie contiene enlace a `https://www.weatherapi.com/`. |
| FT-06 | `/clima/actual` 503 → encabezado sin línea de clima, sin romper la página. |

### 2.6 E2E (Playwright, viewport 360×800 y 1280×800)

| ID | Flujo |
|----|-------|
| E2E-01 | Abrir `/` → ver 3 tarjetas con números → abrir "¿Por qué este número?" → ver 4 factores. |
| E2E-02 | Ir a "Histórico" → gráfico visible con leyenda "Datos sintéticos". |
| E2E-03 | Sin scroll horizontal a 360 px. |

## 3. Pruebas no automatizadas (checklist de entrega)

- [ ] `http://<EC2_HOST>/` abre desde un celular con datos móviles.
- [ ] `http://<EC2_HOST>/docs` muestra Swagger con los 5 endpoints.
- [ ] Reiniciar la EC2 desde la consola → la app vuelve sola (CA-DEP-4).
- [ ] Abrir un PR con un test roto → el check `CI` queda en rojo y no se despliega (CA-DEP-3).
- [ ] `docker history ghcr.io/<owner>/cueva-api:<sha>` no muestra la llave (CA-DEP-6).
- [ ] Rollback con `workflow_dispatch` a un SHA anterior funciona.

## 4. Definición de "Hecho" (DoD)

Una historia está **hecha** cuando: su código está en `main`, todos sus casos de este plan pasan en CI, el despliegue a EC2 fue exitoso y el smoke test pasó.
