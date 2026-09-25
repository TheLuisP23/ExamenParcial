# 10 · Plan de tareas por agente y trazabilidad

> Orden sugerido. Cada tarea = 1 rama `feature/<ID>-<slug>` = 1 PR.
> Las tareas `INF-*` las ejecuta la persona (consola de AWS / GitHub), no un agente.

## 1. Tareas

### Fase 0 · Infraestructura (persona)

| ID | Tarea | Spec |
|----|-------|------|
| INF-01 | Crear cuenta en WeatherAPI.com y obtener la llave. | 05 |
| INF-02 | Lanzar EC2 Ubuntu 24.04 con `infra/ec2/bootstrap.sh` como user data, security group y Elastic IP. | 07 §2 |
| INF-03 | Crear environment `production`, secrets (`EC2_USER`, `EC2_SSH_KEY`, `WEATHERAPI_KEY`) y variable de repo `EC2_HOST`. | 07 §3 |
| INF-04 | Proteger `main`: PR obligatorio + check `CI` requerido. | 00 §4 |

### Fase 1 · Backend (agente **backend**)

| ID | Tarea | Requisitos | Depende de |
|----|-------|-----------|-----------|
| BE-01 | Esqueleto FastAPI, `config.py`, `/health`, Dockerfile (usuario no root, `ARG APP_VERSION`). | RF-09, RNF-06 | — |
| BE-02 | `domain/factors.py` y `domain/holidays.py` + `config/*.yaml`. | RF-02 | BE-01 |
| BE-03 | `domain/predictor.py` (fórmula, rango, nivel, advertencias). | RF-02..04, RF-11 | BE-02 |
| BE-04 | `data/generator.py` + `repository.py` + tablas SQLite. | RF-07 | BE-02 |
| BE-05 | `clients/weatherapi.py` con caché, timeout, reintentos. | RF-01, RF-06 | BE-01 |
| BE-06 | Routers `/predicciones`, `/clima/actual`, `/historico/mensual`, `/modelo` + manejo de errores. | RF-01..08 | BE-03..05 |
| BE-07 | Logs JSON y ocultamiento de la llave. | RNF-05, RNF-10 | BE-05 |

### Fase 2 · Frontend (agente **frontend**)

| ID | Tarea | Requisitos | Depende de |
|----|-------|-----------|-----------|
| FE-01 | Vite + React + TS, tipos generados desde `openapi.yaml`, Dockerfile multi-stage con `infra/nginx/default.conf`. | — | — |
| FE-02 | `TarjetaDia`, `ChipNivel`, `DesgloseFactores`, `Advertencias`. | HU-01..03 | FE-01 |
| FE-03 | `Encabezado` con clima actual, `PiePagina` con atribución y versión. | RF-10 | FE-01 |
| FE-04 | `GraficoHistorico`. | HU-04 | FE-01 |
| FE-05 | Estados de carga/error/sin clima y responsive. | RNF-13 | FE-02 |

### Fase 3 · QA (agente **qa**)

| ID | Tarea | Casos |
|----|-------|-------|
| QA-01 | Fixtures de WeatherAPI anonimizadas. | 05 §6 |
| QA-02 | Tests unitarios del modelo, feriados y generador. | UT-01..35 |
| QA-03 | Tests de integración y contrato (Schemathesis). | IT-01..13 |
| QA-04 | Tests de componentes frontend. | FT-01..06 |
| QA-05 | E2E Playwright. | E2E-01..03 |
| QA-06 | Ejecutar el checklist manual post-deploy y registrar evidencias (capturas) en `docs/evidencias/`. | 08 §3 |

> El agente QA puede escribir los tests de QA-02 **antes** que BE-02/BE-03 (TDD): la tabla dorada ya define el comportamiento.

### Fase 4 · Despliegue

| ID | Tarea | Responsable |
|----|-------|-------------|
| DEP-01 | Primer push a `main` → verificar CA-DEP-1..2 en la pestaña Actions. | persona |
| DEP-02 | Probar rollback (CA-DEP / 07 §4.3). | persona + qa |

## 2. Matriz de trazabilidad

| Requisito | Historia | Tareas | Pruebas |
|-----------|----------|--------|---------|
| RF-01 | HU-01, HU-02 | BE-05, BE-06 | IT-01, IT-06 |
| RF-02 | HU-01 | BE-02, BE-03 | UT-01..11 |
| RF-03 | HU-01 | BE-03 | UT-01..07, UT-13 |
| RF-04 | HU-03 | BE-03, FE-02 | UT-12, E2E-01 |
| RF-05 | HU-02 | BE-06 | IT-02, IT-03, IT-12 |
| RF-06 | HU-01 | BE-05 | IT-04, IT-05, IT-07, FT-03 |
| RF-07 | HU-04 | BE-04 | UT-30..35 |
| RF-08 | HU-04 | BE-06, FE-04 | IT-11, E2E-02 |
| RF-09 | HU-05 | BE-01 | IT-10, smoke |
| RF-10 | — | FE-03 | FT-05 |
| RF-11 | HU-01 | BE-03 | IT-08, IT-09 |
| RNF-05 | — | BE-07 | IT-13, CA-DEP-6 |
| RNF-13 | — | FE-05 | E2E-03 |
| CA-DEP-1..6 | HU-05 | INF-*, DEP-* | smoke, checklist 08 §3 |
