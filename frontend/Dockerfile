# syntax=docker/dockerfile:1
#
# Build context: la RAÍZ del repo (ver docker-compose.yml → services.web.build:
# {context: ., dockerfile: frontend/Dockerfile}). Por eso las rutas COPY son
# relativas a la raíz, no a frontend/.
#
# La configuración de Nginx vive en infra/nginx/default.conf (fuente única,
# no se duplica aquí: en Windows sin privilegios de administrador no se puede
# crear el symlink frontend/nginx.conf -> ../infra/nginx/default.conf que
# describe specs/06-frontend.md §5, así que este Dockerfile copia el archivo
# real directamente).

# --- Etapa 1: build ---------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# --- Etapa 2: runtime (Nginx sirve la SPA + proxy hacia /api) --------------
FROM nginx:1.27-alpine AS final

COPY --from=builder /build/dist /usr/share/nginx/html
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
