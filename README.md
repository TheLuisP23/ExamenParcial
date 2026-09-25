# 🦉 Cueva de las Lechuzas · Predictor de visitantes

Estima cuántas personas visitarán la **Cueva de las Lechuzas** (Parque Nacional Tingo María,
Huánuco, Perú) hoy y los próximos 2 días, según el pronóstico de **WeatherAPI.com**.
Se despliega automáticamente en **AWS EC2** con **GitHub Actions**.

> ⚠️ Los datos de visitas son **sintéticos**, calibrados con la cifra anual pública del parque.
> La justificación está en [`specs/02-decision-datos.md`](specs/02-decision-datos.md).

## Especificaciones

| # | Documento | Contenido |
|---|-----------|-----------|
| 00 | [Constitución](specs/00-constitucion.md) | Principios, stack, convenciones, glosario |
| 01 | [Producto](specs/01-producto.md) | Problema, usuarios, alcance, historias con criterios Gherkin, requisitos funcionales |
| 02 | [Decisión de datos (ADR)](specs/02-decision-datos.md) | Banco existente vs API vs dataset autogenerado → **autogenerado**; esquema SQLite |
| 03 | [Modelo de predicción](specs/03-modelo-prediccion.md) | Fórmula, factores, niveles, advertencias, tabla dorada de pruebas |
| 04 | [API](specs/04-api.md) + [OpenAPI](specs/openapi.yaml) | Contrato REST, errores, estructura del backend |
| 05 | [Integración WeatherAPI](specs/05-integracion-weatherapi.md) | Endpoints, mapeo de campos, límites del plan, resiliencia |
| 06 | [Frontend](specs/06-frontend.md) | Pantalla, componentes, estados, accesibilidad |
| 07 | [Infraestructura y despliegue](specs/07-infraestructura-despliegue.md) | Arquitectura AWS, pipelines, secretos, criterios de despliegue |
| 08 | [Plan de pruebas](specs/08-plan-pruebas.md) | Pirámide, casos UT/IT/FT/E2E, checklist, DoD |
| 09 | [Requisitos no funcionales](specs/09-requisitos-no-funcionales.md) | Rendimiento, seguridad, costo, observabilidad |
| 10 | [Tareas y trazabilidad](specs/10-tareas-y-trazabilidad.md) | Tareas por agente y matriz requisito → tarea → prueba |

## Arquitectura

```
GitHub (push a main) ─▶ Actions: CI ─▶ build imágenes ─▶ GHCR ─▶ SSH a EC2 ─▶ docker compose up ─▶ smoke test
EC2:  Nginx :80 ──┬── /        → SPA React
                  └── /api/v1  → FastAPI ──▶ WeatherAPI.com
                                      └──▶ SQLite (dataset sintético + caché)
```

## Puesta en marcha del despliegue (una sola vez)

1. **WeatherAPI:** crea una cuenta en https://www.weatherapi.com/ y copia tu API key.
2. **EC2:** lanza Ubuntu 24.04 (x86_64, t3.micro/t2.micro), key pair `cueva-deploy`,
   security group con puertos 22 y 80, y pega [`infra/ec2/bootstrap.sh`](infra/ec2/bootstrap.sh)
   en *User data*. Asocia una **Elastic IP**.
3. **GitHub → Settings → Environments → `production`** → secrets:
   `EC2_USER` (`ubuntu`), `EC2_SSH_KEY` (contenido del `.pem`), `WEATHERAPI_KEY`.
4. **GitHub → Settings → Secrets and variables → Actions → Variables** → `EC2_HOST` = Elastic IP.
5. Push a `main` → pestaña **Actions** → al terminar, abre `http://<EC2_HOST>/`.

## Correr en local

```bash
cp .env.example .env        # pon tu WEATHERAPI_KEY
docker compose up --build   # http://localhost  ·  http://localhost/docs
```

## Desarrollo con agentes

Ver [`CLAUDE.md`](CLAUDE.md): cada agente (backend, frontend, qa) lee la constitución, su spec y
toma tareas de `specs/10-tareas-y-trazabilidad.md`.

---
Clima: [Powered by WeatherAPI.com](https://www.weatherapi.com/)
