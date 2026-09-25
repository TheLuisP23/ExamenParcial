# 06 · Especificación del frontend

## 1. Pantalla única (SPA) — estructura

```
┌──────────────────────────────────────────────────────────────┐
│ 🦉 Cueva de las Lechuzas · ¿Cuánta gente irá?                │
│ PN Tingo María, Huánuco · Clima ahora: 27 °C, Parcialmente…  │
├──────────────────────────────────────────────────────────────┤
│ ┌──────────┐  ┌──────────┐  ┌──────────┐                     │
│ │ HOY      │  │ MAÑANA   │  │ DOM 27   │   ← TarjetaDia × 3  │
│ │ vie 25   │  │ sáb 26   │  │          │                     │
│ │ ☁ 12 mm  │  │ ☀ 0 mm   │  │ ⛈ 55 mm  │                     │
│ │   426    │  │   609    │  │   142    │   número grande     │
│ │ 341–511  │  │ 487–731  │  │ 114–170  │                     │
│ │ [Alta]   │  │ [M. alta]│  │ [Baja]   │   chip de nivel     │
│ │ ▸ ¿Por qué este número?                │   desplegable     │
│ └──────────┘  └──────────┘  └──────────┘                     │
│ ⚠ Tormenta eléctrica pronosticada en horario de visita.      │
├──────────────────────────────────────────────────────────────┤
│ Histórico (datos sintéticos)  [gráfico de barras 36 meses]   │
├──────────────────────────────────────────────────────────────┤
│ Horario 08:00–17:00 · Datos sintéticos con fines académicos  │
│ Powered by WeatherAPI.com · versión a1b2c3d                  │
└──────────────────────────────────────────────────────────────┘
```

## 2. Componentes

| Componente | Props / datos | Reglas |
|------------|---------------|--------|
| `Encabezado` | `/clima/actual` | Si responde 503, ocultar la línea de clima actual (no romper la página). |
| `TarjetaDia` | un elemento de `predicciones[]` | Título: "Hoy", "Mañana" o día abreviado (`es-PE`). Número con separador de miles (`1 024`). |
| `ChipNivel` | `nivel_afluencia` | Colores: Baja = verde, Media = azul, Alta = ámbar, Muy alta = rojo. Siempre con texto (no solo color). |
| `DesgloseFactores` | `factores` | Lista: "Base 350 → × 1.20 temporada (Julio…) → … = 426". Cerrado por defecto; accesible con teclado (`<details>`). |
| `Advertencias` | `advertencias[]` de los 3 días | Banda con `role="alert"`; una línea por advertencia con la fecha. |
| `GraficoHistorico` | `/historico/mensual` | Barras por mes; eje Y "visitantes/mes"; subtítulo "Datos sintéticos". Librería: Recharts. |
| `PiePagina` | `/health` | Atribución con enlace a https://www.weatherapi.com/ (RF-10), versión desplegada. |

## 3. Estados

| Estado | Qué se muestra |
|--------|----------------|
| Cargando | Esqueletos (skeleton) en las 3 tarjetas. |
| `clima_disponible=false` | Tarjeta con ícono "sin datos", texto "Estimación solo con calendario". |
| Error de red / 5xx en `/predicciones` | Mensaje "No pudimos calcular la predicción. Reintenta en unos minutos." + botón Reintentar. |

## 4. Requisitos no funcionales del front

- **Responsive:** 1 columna < 640 px; 3 columnas ≥ 640 px. Sin scroll horizontal a 360 px.
- **Accesibilidad:** contraste AA, `lang="es"`, imágenes del clima con `alt` = texto de la condición.
- **Rendimiento:** bundle JS inicial < 250 KB gzip. Lighthouse Performance ≥ 85 en móvil.
- **Configuración:** la URL base de la API es relativa (`/api/v1`); no se hardcodea el host.
- **Sin secretos:** el front **nunca** llama a WeatherAPI directamente ni conoce la llave.

## 5. Estructura

```
frontend/
├── src/
│   ├── api/client.ts         # fetch tipado (tipos generados desde openapi.yaml con openapi-typescript)
│   ├── components/…          # los de la tabla §2
│   ├── App.tsx
│   └── main.tsx
├── tests/                    # Vitest + Testing Library
├── nginx.conf → ../infra/nginx/default.conf
├── Dockerfile                # multi-stage: node:20-alpine build → nginx:1.27-alpine
└── package.json
```
