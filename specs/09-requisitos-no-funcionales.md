# 09 · Requisitos no funcionales

| ID | Categoría | Requisito | Cómo se verifica |
|----|-----------|-----------|------------------|
| RNF-01 | Rendimiento | `/predicciones` responde en < 500 ms p95 con caché caliente y < 6 s con caché fría. | Test de integración con `time`; `curl -w %{time_total}` en smoke. |
| RNF-02 | Rendimiento | `/health` responde en < 300 ms. | Smoke test. |
| RNF-03 | Disponibilidad | La app se recupera sola tras reinicio del contenedor o de la instancia. | CA-DEP-4. |
| RNF-04 | Resiliencia | Caída de WeatherAPI no tumba `/predicciones` (degrada). | IT-04. |
| RNF-05 | Seguridad | Ningún secreto en repo, imágenes, logs ni respuestas. | IT-13, CA-DEP-6, GitHub secret scanning activado. |
| RNF-06 | Seguridad | Contenedor `api` corre como usuario no root. | `docker compose exec api id -u` ≠ 0. |
| RNF-07 | Seguridad | Dependencias sin vulnerabilidades críticas conocidas. | Dependabot activado para `pip`, `npm`, `github-actions` y `docker`. |
| RNF-08 | Costo | Consumo de WeatherAPI < 10 % de la cuota gratuita (< 10 000 llamadas/mes). | Caché de 30 min; métrica en logs. |
| RNF-09 | Costo | Infraestructura en una sola instancia micro; sin servicios de pago adicionales. | Revisión de la consola de AWS. |
| RNF-10 | Observabilidad | Logs en JSON a stdout con `nivel`, `ruta`, `status`, `duracion_ms`, `version`. | `docker compose logs api`. |
| RNF-11 | Mantenibilidad | Coeficientes del modelo, feriados y coordenadas se cambian editando `config/*.yaml`, sin tocar código. | Revisión de código. |
| RNF-12 | Portabilidad | `docker compose up` con `docker-compose.yml` local levanta todo en cualquier máquina con Docker. | README → "Correr en local". |
| RNF-13 | Usabilidad | UI usable a 360 px de ancho, contraste AA, textos en español. | E2E-03, Lighthouse Accessibility ≥ 90. |
| RNF-14 | Honestidad | Toda vista con números de visitas indica que son sintéticos. | FT y revisión manual. |
