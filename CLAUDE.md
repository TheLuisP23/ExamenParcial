# Instrucciones para agentes (back · front · qa)

Este repo se desarrolla **guiado por specs**. Antes de escribir código, lee en este orden:

1. `specs/00-constitucion.md` — reglas no negociables, stack y convenciones.
2. La spec de tu área (tabla de abajo).
3. `specs/10-tareas-y-trazabilidad.md` — toma **una** tarea con tu prefijo, en orden.

| Agente | Specs que le corresponden | Prefijo de tareas | Carpeta |
|--------|---------------------------|-------------------|---------|
| `back` | 02, 03, 04, `openapi.yaml`, 05, 09 | `BE-` | `backend/`, `config/` |
| `front` | 01 (HU), 04 (contrato), 06, 09 | `FE-` | `frontend/` |
| `qa` | 01 (criterios Gherkin), 03 §5, 08, 09 | `QA-` | `backend/tests/`, `frontend/tests/`, `e2e/` |

## Cómo delegar (agente principal)

- Tareas `BE-*` → subagente `back` · `FE-*` → `front` · `QA-*` → `qa`.
- Una tarea por invocación. Al volver, revisa el reporte y corre los tests antes de pasar a la siguiente.
- Si un subagente devuelve una pregunta, házsela al usuario; no decidas por él.

## Reglas de trabajo

- **No inventes requisitos.** Si algo no está en `specs/`, detente y propón el cambio a la spec en el PR (sección "Cambios de spec").
- **El contrato manda:** `specs/openapi.yaml`. Backend lo implementa, frontend genera tipos desde él, QA lo valida con Schemathesis.
- **Coeficientes en `config/`**, nunca literales en el código (P7).
- **Nombra los tests con el ID** del caso: `test_UT_08_bordes_de_lluvia`, `it("FT-03 sin clima …")`.
- **Nunca** llames a la WeatherAPI real en tests; usa las fixtures de `backend/tests/fixtures/weatherapi/`.
- **Nunca** imprimas ni registres `WEATHERAPI_KEY`.
- No modifiques `.github/workflows/`, `docker-compose.prod.yml` ni `infra/` salvo que la tarea lo pida.
- Cada PR incluye: tarea (`BE-03`), requisitos cubiertos (`RF-02, RF-04`) y casos de prueba que pasan.

## Comandos

```bash
# backend
cd backend && pip install -e ".[dev]" && pytest
uvicorn app.main:app --reload            # http://localhost:8000/docs

# frontend
cd frontend && npm ci && npm run dev     # http://localhost:5173 (proxy /api → :8000)

# todo junto
docker compose up --build                # http://localhost
```
