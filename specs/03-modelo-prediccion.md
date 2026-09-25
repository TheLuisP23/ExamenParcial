# 03 · Modelo de predicción de visitantes (`reglas-v1`)

## 1. Fórmula

```
estimado = min( capacidad_diaria,
                ROUND_HALF_UP( base_diaria
                               × f_temporada(fecha)
                               × f_dia_semana(fecha)
                               × f_feriado(fecha)
                               × f_clima(pronostico) ) )

rango_min = ROUND_HALF_UP(estimado × 0.80)
rango_max = min(capacidad_diaria, ROUND_HALF_UP(estimado × 1.20))
```

- `base_diaria` se lee de la tabla `model_params` (la calcula el generador, ver `02-decision-datos.md` §4.2).
- `capacidad_diaria` = **1 500** (supuesto operativo, configurable). Si el tope se aplica, el desglose incluye `"tope_capacidad_aplicado": true`.
- Todos los coeficientes están en `config/model.yaml`. Los valores de abajo son los **por defecto**.
- Un modelo es **puro**: mismas entradas → misma salida. No lee la hora del sistema; la fecha se inyecta.

## 2. Factores

### 2.1 `f_temporada` (por mes)

| Ene | Feb | Mar | Abr | May | Jun | Jul | Ago | Sep | Oct | Nov | Dic |
|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| 1.10 | 1.10 | 0.90 | 0.95 | 0.95 | 1.00 | 1.20 | 1.10 | 0.95 | 0.90 | 0.90 | 1.05 |

Razón: vacaciones escolares de verano (ene–feb), vacaciones de medio año y Fiestas Patrias (jul–ago), temporada seca (may–sep).

### 2.2 `f_dia_semana`

| Lun | Mar | Mié | Jue | Vie | Sáb | Dom |
|-----|-----|-----|-----|-----|-----|-----|
| 0.75 | 0.70 | 0.70 | 0.80 | 0.95 | 1.45 | 1.50 |

Si la fecha es feriado, se usa el valor de **sábado** (1.45) salvo que sea domingo (1.50).

### 2.3 `f_feriado`

| Situación | Factor |
|-----------|--------|
| Día normal | 1.00 |
| Feriado nacional aislado | 1.35 |
| Día dentro de un **feriado largo** (bloque ≥ 3 días seguidos no laborables formado por feriados y fin de semana, incl. Jueves y Viernes Santo) | 1.60 |

- Feriados en `config/holidays_pe.yaml`, por año. Deben revisarse contra el calendario oficial de cada año (incluye los días no laborables que decrete el Ejecutivo).
- Un sábado o domingo que forma parte de un feriado largo también recibe 1.60.

### 2.4 `f_clima`

```
f_clima = max(0.30, f_lluvia × f_horario × f_tormenta × f_calor × f_dia_seco)
```

| Sub-factor | Regla (campos de WeatherAPI) | Valor |
|-----------|------------------------------|-------|
| `f_lluvia` | `day.totalprecip_mm` < 2 | 1.00 |
| | 2 ≤ mm < 10 | 0.90 |
| | 10 ≤ mm < 25 | 0.70 |
| | 25 ≤ mm < 50 | 0.50 |
| | mm ≥ 50 | 0.35 |
| `f_horario` | ≥ 4 horas entre 08:00 y 16:00 con `hour[].chance_of_rain` ≥ 70 | 0.85; si no, 1.00 |
| `f_tormenta` | `day.condition.code` o algún `hour[].condition.code` (08–17 h) ∈ {1087, 1273, 1276, 1279, 1282} | 0.80; si no, 1.00 |
| `f_calor` | `day.maxtemp_c` ≥ 34 | 0.90; si no, 1.00 |
| `f_dia_seco` | `day.totalprecip_mm` < 1 **y** `day.daily_chance_of_rain` < 30 | 1.05; si no, 1.00 |

- Si WeatherAPI no está disponible (RF-06): `f_clima = 1.00` y razón `"Clima no disponible"`.
- En el **generador** (datos sintéticos, sin horas) `f_horario = 1.00` y `f_dia_seco` usa solo `precip_mm < 1`.

## 3. Nivel de afluencia

Se calcula con **percentiles del dataset sintético** (tabla `daily_visits`), recalculados al generar:

| Nivel | Condición |
|-------|-----------|
| Baja | estimado ≤ P25 |
| Media | P25 < estimado ≤ P75 |
| Alta | P75 < estimado ≤ P95 |
| Muy alta | estimado > P95 |

## 4. Advertencias (RF-11)

La lista `advertencias` de la respuesta incluye, si aplica:

| Código | Condición | Texto |
|--------|-----------|-------|
| `LLUVIA_EXTREMA` | `totalprecip_mm` ≥ 50 | "Lluvia muy intensa: posible cierre o restricción de senderos." |
| `TORMENTA` | `f_tormenta` = 0.80 | "Tormenta eléctrica pronosticada en horario de visita." |
| `ALERTA_OFICIAL` | `alerts.alert` no vacío (con `alerts=yes`) | Texto `headline` de la alerta. |
| `CLIMA_NO_DISPONIBLE` | RF-06 | "No pudimos obtener el clima." |

## 5. Casos de prueba de referencia (tabla dorada)

Con `base_diaria = 350` inyectada y config por defecto. **El agente QA debe convertir esta tabla en un test parametrizado.**

| # | Fecha | Día | Clima de entrada | Factores esperados (temp × día × feriado × clima) | Estimado | Rango |
|---|-------|-----|------------------|---------------------------------------------------|----------|-------|
| T1 | 2026-07-18 | sáb | 12 mm, sin tormenta, 29 °C, chance 60 | 1.20 × 1.45 × 1.00 × 0.70 | **426** | 341 – 511 |
| T2 | 2026-03-10 | mar | 0.5 mm, chance 10, 28 °C | 0.90 × 0.70 × 1.00 × 1.05 | **232** | 186 – 278 |
| T3 | 2026-10-18 | dom | 55 mm, tormenta, 27 °C | 0.90 × 1.50 × 1.00 × max(0.30, 0.35×0.80) = 0.30 | **142** | 114 – 170 |
| T4 | 2026-12-25 | vie (feriado largo vie-sáb-dom) | 1.5 mm, chance 40, 30 °C | 1.05 × 1.45 × 1.60 × 1.00 | **853** | 682 – 1 024 |
| T5 | 2026-07-18 | sáb | WeatherAPI caído | 1.20 × 1.45 × 1.00 × 1.00 | **609** | 487 – 731 |
| T6 | 2026-12-25 | vie | 0 mm, chance 5, 30 °C, `base_diaria = 700` | 1.05 × 1.45 × 1.60 × 1.05 = 2.5578 → 1 790.46 | **1 500** (tope) | 1 200 – 1 500 |
| T7 | 2026-05-12 | mar | 8 mm, 5 horas 08–16 con chance ≥ 70, 35 °C | 0.95 × 0.70 × 1.00 × (0.90×0.85×0.90 = 0.6885) | **160** | 128 – 192 |

Verificación T7: 350 × 0.95 × 0.70 × 0.6885 = 160.24 → 160.

## 6. Evolución (fuera del MVP)

`ml-v2`: regresión de Poisson entrenada sobre `daily_visits` con las mismas variables. Solo se adopta si su MAE en validación temporal (último año) es menor al de `reglas-v1`. El campo `version_modelo` en la respuesta permite convivir con ambas.
