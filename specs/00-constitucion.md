# 00 · Constitución del proyecto

> Reglas que **todo** agente (backend, frontend, qa) y toda persona debe respetar.
> Si una spec posterior contradice este documento, gana este documento.

## 1. Propósito

Estimar **cuántas personas visitarán la Cueva de las Lechuzas** (Parque Nacional
Tingo María, Huánuco, Perú) en un día dado, usando el **pronóstico del clima de
WeatherAPI.com** y factores de calendario, y exponerlo como una aplicación web
desplegada en **AWS EC2** mediante **GitHub Actions**.

## 2. Principios

| # | Principio | Consecuencia práctica |
|---|-----------|-----------------------|
| P1 | **Spec primero** | Ningún código se escribe sin una spec en `specs/` que lo pida. Si falta algo, se actualiza la spec antes que el código. |
| P2 | **Trazabilidad** | Cada requisito tiene un ID (`RF-xx`, `RNF-xx`, `HU-xx`). Cada test referencia al menos un ID en su nombre o docstring. |
| P3 | **Transparencia del modelo** | La predicción siempre se devuelve con los factores que la explican. Nada de "caja negra". |
| P4 | **Honestidad de datos** | Los datos de visitas son **sintéticos** (ver `02-decision-datos.md`) y la UI y la API lo dicen explícitamente. |
| P5 | **Secretos fuera del repo** | `WEATHERAPI_KEY`, llaves SSH y tokens viven solo en GitHub Secrets y en el `.env` del servidor. Nunca en código, logs ni en respuestas de la API. |
| P6 | **Despliegue reproducible** | Todo lo que corre en EC2 sale de una imagen Docker construida por GitHub Actions. Nada se instala "a mano" salvo el bootstrap documentado. |
| P7 | **Configuración, no constantes** | Coeficientes del modelo, coordenadas, horarios y feriados viven en `config/`, no dentro del código. |

## 3. Stack decidido

| Capa | Tecnología | Motivo |
|------|------------|--------|
| Backend | Python 3.12 + FastAPI + httpx + Pydantic v2 | Genera OpenAPI automáticamente; Python facilita el generador de datos y el modelo. |
| Persistencia | SQLite (archivo en volumen Docker) | El dataset es pequeño (~1 100 filas); no justifica RDS. Ver ADR-02. |
| Frontend | Vite + React + TypeScript, servido por Nginx | Build estático; Nginx además hace de proxy inverso hacia `/api`. |
| Contenedores | Docker + Docker Compose v2 | Una sola orden levanta todo en EC2. |
| Registro de imágenes | GitHub Container Registry (GHCR) | Sin configurar IAM extra; el `GITHUB_TOKEN` basta. Ver ADR-04. |
| CI/CD | GitHub Actions | Requisito del encargo. |
| Nube | AWS EC2 (Ubuntu 24.04 LTS, t3.micro o t2.micro) + Elastic IP | Requisito del encargo. |
| Pruebas | pytest, respx (mock HTTP), Vitest, Playwright | Ver `08-plan-pruebas.md`. |


## 4. Convenciones

- Idioma: código y nombres técnicos en inglés; textos de UI, specs y mensajes de error en español.
- Zona horaria de negocio: **America/Lima (UTC-5)**. "Hoy" siempre es hoy en Lima, nunca en UTC.
- Fechas en la API: ISO 8601 `YYYY-MM-DD`.
- Commits: Conventional Commits (`feat:`, `fix:`, `test:`, `ci:`, `docs:`).
- Ramas: `main` (protegida, despliega) ← `feature/<id-requisito>-<slug>` vía Pull Request.
- Un PR no se fusiona si falla el workflow `ci.yml`.

## 5. Glosario

| Término | Definición |
|---------|-----------|
| **Visitantes estimados** | Número entero de personas que se espera ingresen al sector Cueva de las Lechuzas entre 08:00 y 17:00. |
| **Factor** | Multiplicador adimensional (0 – 2) que ajusta la base diaria por clima, temporada, día de semana o feriado. |
| **Base diaria** | Promedio de visitantes de un día "neutro" (clima bueno, día laborable, temporada media). |
| **Dataset sintético** | Histórico autogenerado por `backend/app/data/generator.py` con semilla fija. |
| **Horario de visita** | 08:00 – 17:00 (hora de Lima), todos los días (fuente: SERNANP). |
