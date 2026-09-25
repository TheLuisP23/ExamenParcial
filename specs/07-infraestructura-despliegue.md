# 07 · Infraestructura y despliegue (AWS EC2 + GitHub Actions)

## 1. Arquitectura

```
 Desarrollador ──push/PR──▶ GitHub ──▶ GitHub Actions
                                         │
            ┌────────────────────────────┼─────────────────────────────┐
            │ ci.yml (PR y push)         │ deploy.yml (push a main)    │
            │  • tests backend (pytest)  │  1. reutiliza ci.yml        │
            │  • tests frontend (vitest) │  2. build + push imágenes   │
            │  • lint + build Docker     │     → ghcr.io (tag = SHA)   │
            └────────────────────────────┤  3. ssh a EC2: compose pull │
                                         │     + up -d                 │
                                         │  4. smoke test /health      │
                                         └──────────────┬──────────────┘
                                                        │ SSH (22)
                                                        ▼
                    ┌───────────────── AWS · EC2 Ubuntu 24.04 (Elastic IP) ─────────────────┐
  Usuario ──HTTP:80──▶  contenedor `web` (Nginx)                                            │
                    │     ├── /            → SPA estática (React)                           │
                    │     └── /api/, /docs → proxy ─▶ contenedor `api` (FastAPI :8000)       │
                    │                                   ├── volumen `cueva-data` (SQLite)   │
                    │                                   └── HTTPS ─▶ api.weatherapi.com     │
                    └──────────────────────────────────────────────────────────────────────┘
```

## 2. Recursos de AWS (creación manual, una sola vez)

| Recurso | Configuración | Motivo |
|---------|---------------|--------|
| EC2 | Ubuntu Server 24.04 LTS, **x86_64**, `t3.micro` (o `t2.micro`), 20 GB gp3 | Suficiente para 2 contenedores livianos. Si eliges Graviton (`t4g`), cambia `platforms` a `linux/arm64` en `deploy.yml`. |
| Key pair | ED25519, nombre `cueva-deploy` | La privada va al secret `EC2_SSH_KEY`. |
| Security Group `cueva-sg` | Entrante: **80/tcp** 0.0.0.0/0 · **22/tcp** 0.0.0.0/0 (ver riesgo R1). Saliente: todo. | HTTP público; SSH para el deploy desde runners de GitHub (IPs dinámicas). |
| Elastic IP | Asociada a la instancia | La IP no cambia al reiniciar; `EC2_HOST` queda fijo. |
| User data | `infra/ec2/bootstrap.sh` | Instala Docker + Compose y crea `/opt/cueva`. |

## 3. Secretos y variables en GitHub

Crear el environment **`production`** (Settings → Environments) y cargar ahí los *secrets*. La *variable* `EC2_HOST` va a nivel de **repositorio** (Settings → Secrets and variables → Actions → Variables) porque la usan también jobs sin environment (`smoke`).

| Nombre | Tipo | Valor |
|--------|------|-------|
| `EC2_HOST` | **Variable de repositorio** (no es secreto; así la URL aparece en *Deployments*) | Elastic IP (ej. `3.95.10.20`) |
| `EC2_USER` | Secret | `ubuntu` |
| `EC2_SSH_KEY` | Secret | Contenido completo de la llave privada `cueva-deploy.pem` |
| `WEATHERAPI_KEY` | Secret | Llave de WeatherAPI.com |

`GITHUB_TOKEN` (automático) se usa para publicar y descargar imágenes de GHCR.

## 4. Pipelines

### 4.1 `ci.yml` — calidad (en cada PR y push)

| Job | Pasos | Falla si… |
|-----|-------|-----------|
| `backend` | setup Python 3.12 → `pip install -e .[dev]` → `ruff check` → `pytest --cov --cov-fail-under=80` | lint, test o cobertura < 80 % |
| `frontend` | setup Node 20 → `npm ci` → `npm run lint` → `npm test` → `npm run build` | cualquier paso |
| `contract` | valida `specs/openapi.yaml` (Redocly CLI) | OpenAPI inválido |
| `docker` | `docker build` de ambas imágenes (sin push) | Dockerfile roto |

### 4.2 `deploy.yml` — despliegue continuo (push a `main` o manual)

| Job | Depende de | Qué hace |
|-----|-----------|----------|
| `ci` | — | Reutiliza `ci.yml` (`workflow_call`). |
| `build-push` | `ci` | Construye y publica `ghcr.io/<owner>/cueva-api` y `cueva-web` con tags `<sha>` y `latest`. |
| `deploy` | `build-push` | Copia `docker-compose.prod.yml` a `/opt/cueva`, escribe `.env`, hace `docker compose pull && up -d`, limpia imágenes viejas. |
| `smoke` | `deploy` | `curl` a `/api/v1/health` (espera `version == <sha corto>`), `/api/v1/predicciones` (HTTP 200) y `/` (HTTP 200). Hasta 10 intentos cada 6 s. |

- `concurrency: production` evita dos despliegues simultáneos.
- El environment `production` muestra la URL pública en la pestaña *Deployments* del repo.

### 4.3 Rollback

Re-ejecutar `deploy.yml` manualmente (`workflow_dispatch`) indicando `image_tag = <sha anterior>`. El job salta `ci` y `build-push` si se pasa un tag.

## 5. Criterios de aceptación del despliegue

- **CA-DEP-1:** Un push a `main` con tests verdes deja la nueva versión sirviendo en `http://<EC2_HOST>/` en menos de 10 minutos, sin pasos manuales.
- **CA-DEP-2:** `GET http://<EC2_HOST>/api/v1/health` devuelve la `version` igual al SHA corto del último commit de `main`.
- **CA-DEP-3:** Un PR con un test fallando **no** puede desplegarse (el job `ci` falla y `build-push` no corre).
- **CA-DEP-4:** Reiniciar la instancia EC2 vuelve a levantar la app sola (`restart: unless-stopped` + Docker habilitado en systemd).
- **CA-DEP-5:** El dataset sintético sobrevive a un redeploy (volumen `cueva-data`).
- **CA-DEP-6:** `WEATHERAPI_KEY` no aparece en el repo, en los logs de Actions (enmascarado) ni en las imágenes Docker (`docker history` no la muestra).

## 6. Riesgos y mejoras

| ID | Riesgo | Mitigación actual | Mejora futura |
|----|--------|-------------------|---------------|
| R1 | Puerto 22 abierto a Internet | Solo autenticación por llave, `PasswordAuthentication no` | AWS SSM Run Command + OIDC (sin SSH) |
| R2 | Sin HTTPS | Aceptable para el parcial | Dominio + Caddy/Let's Encrypt o ALB + ACM |
| R3 | Una sola instancia (sin HA) | `restart: unless-stopped` | ASG + ALB; SQLite → RDS |
| R4 | Imágenes en GHCR privadas | El deploy hace `docker login` con `GITHUB_TOKEN` | Hacer públicos los paquetes o migrar a ECR con OIDC |
| R5 | Costo | Instancia pequeña; apagar tras la evaluación | Presupuesto con alerta en AWS Budgets |
