# 02 · Decisión de datos (ADR-01)

> El encargo pide **evaluar** si se usa un banco de datos existente, una API existente
> o si se autogenera un banco de datos. Este documento registra esa evaluación.

- **Estado:** Aceptada
- **Fecha:** 2026-09-25
- **Decisores:** equipo del proyecto

## 1. Contexto

Para predecir visitantes necesitamos dos tipos de datos:

| Dato | ¿Qué necesitamos? |
|------|-------------------|
| **Clima** | Pronóstico diario y horario de la cueva. |
| **Visitas** | Histórico de visitantes por día para calibrar el modelo. |

## 2. Opciones evaluadas

### 2.1 Clima

| Opción | Evaluación |
|--------|-----------|
| **API existente: WeatherAPI.com** | ✅ Exigida por el encargo. Plan gratuito: 100 000 llamadas/mes, pronóstico de 3 días, histórico de 1 día. Acepta coordenadas en `q`. |
| Banco de datos propio de clima | ❌ Innecesario: la API ya lo resuelve. |

**Decisión clima:** API existente (WeatherAPI.com), con caché local para no gastar cuota.

### 2.2 Visitas

| Opción | Evaluación | Veredicto |
|--------|-----------|-----------|
| **A. Banco de datos existente** (SERNANP, MINCETUR, datos abiertos) | SERNANP publica cifras **agregadas** del Parque Nacional Tingo María (p. ej. "más de 160 000 turistas" en un año, según su jefatura). **No existe** un registro público **diario** por sector (cueva) ni cruzado con clima. Pedirlo por acceso a la información pública tarda semanas. | ❌ No viable en el plazo del parcial. Se usa **solo para calibrar** el total anual. |
| **B. API existente** de afluencia (p. ej. "popular times" de Google) | No hay API oficial de afluencia; las alternativas son scraping (viola términos de uso) o servicios de pago sin cobertura garantizada en Tingo María. | ❌ Descartada. |
| **C. Banco de datos autogenerado** (sintético) | Se genera un histórico diario de 3 años con reglas de negocio explícitas + ruido aleatorio, **calibrado** al total anual publicado. Reproducible (semilla fija), testeable y honesto si se declara como sintético. | ✅ **Elegida.** |

## 3. Decisión

1. **Clima:** WeatherAPI.com `forecast.json` (en vivo) — ver `05-integracion-weatherapi.md`.
2. **Visitas:** **dataset sintético autogenerado**, calibrado con la cifra pública de SERNANP.
3. **Persistencia:** SQLite en un volumen Docker (ADR-02, abajo).

## 4. Especificación del generador (RF-07)

Archivo: `backend/app/data/generator.py`. Se ejecuta al arrancar si la tabla `daily_visits` está vacía, y también por CLI: `python -m app.data.generator --seed 42 --years 3`.

### 4.1 Parámetros (en `config/model.yaml`)

| Parámetro | Valor por defecto | Origen |
|-----------|-------------------|--------|
| `visitantes_anuales_parque` | 160 000 | Cifra pública del PN Tingo María (jefatura SERNANP, vía prensa). |
| `proporcion_cueva` | 0.80 | **Supuesto**: la cueva es el atractivo principal del parque. Documentado como supuesto. |
| `semilla` | 42 | Reproducibilidad. |
| `anios` | 3 | Suficiente para ver estacionalidad. |
| `ruido_sigma` | 0.15 | Ruido log-normal multiplicativo (≈ ±15 %). |

### 4.2 Algoritmo

```
para cada día d en [hoy - 3 años, ayer]:
    clima_d  ← muestrear_clima_sintético(mes(d))       # ver 4.3
    f        ← f_temporada(d) × f_dia_semana(d) × f_feriado(d) × f_clima(clima_d)
    bruto_d  ← f × exp(N(0, ruido_sigma))
base_diaria ← (visitantes_anuales_parque × proporcion_cueva × anios) / Σ bruto_d
visitantes_d ← min(capacidad_diaria, round(base_diaria × bruto_d))
```

La **misma** función de factores (`03-modelo-prediccion.md`) se usa para generar y para
predecir. Así el histórico y la predicción son coherentes, y la `base_diaria` calculada
se guarda en la tabla `model_params` para que el predictor la use.

### 4.3 Clima sintético por mes

Tingo María es selva alta: cálida todo el año (22–26 °C de promedio según SERNANP) y
con **época de lluvias de octubre a abril**. El generador muestrea por día:

| Variable | Distribución | Parámetros por mes |
|----------|--------------|--------------------|
| `precip_mm` | 0 con prob. `1 - p_lluvia[mes]`; si llueve, Gamma(k=1.5, θ=`mm_medio[mes]`/1.5) | `p_lluvia`: 0.75 (oct–abr), 0.40 (may–sep). `mm_medio`: 18 (oct–abr), 8 (may–sep). |
| `maxtemp_c` | Normal(μ=`tmax[mes]`, σ=1.5) | `tmax`: 30 (may–sep), 29 (oct–abr) |
| `tormenta` | Bernoulli(`p_tormenta[mes]`) | 0.20 (oct–abr), 0.05 (may–sep) |

> Estos valores son **supuestos razonables** para fines académicos y viven en
> `config/climate_synthetic.yaml`. Si se consigue climatología oficial (SENAMHI), se
> reemplazan ahí sin tocar código.

### 4.4 Esquema de la base de datos

```sql
CREATE TABLE daily_visits (
    date          TEXT PRIMARY KEY,      -- YYYY-MM-DD (America/Lima)
    visitors      INTEGER NOT NULL CHECK (visitors >= 0),
    precip_mm     REAL    NOT NULL,
    maxtemp_c     REAL    NOT NULL,
    thunderstorm  INTEGER NOT NULL CHECK (thunderstorm IN (0,1)),
    is_holiday    INTEGER NOT NULL CHECK (is_holiday IN (0,1)),
    synthetic     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE model_params (
    key   TEXT PRIMARY KEY,               -- 'base_diaria', 'semilla', 'generado_en', 'version_modelo'
    value TEXT NOT NULL
);

CREATE TABLE weather_cache (
    cache_key   TEXT PRIMARY KEY,         -- 'forecast:<q>:<dias>'
    payload     TEXT NOT NULL,            -- JSON crudo de WeatherAPI
    fetched_at  TEXT NOT NULL             -- ISO 8601 UTC
);
```

### 4.5 Criterios de aceptación del generador

- **CA-GEN-1:** Con `semilla=42`, dos ejecuciones producen exactamente las mismas filas.
- **CA-GEN-2:** La suma de visitantes de cualquier año completo generado está dentro de ±5 % de `visitantes_anuales_parque × proporcion_cueva` (128 000).
- **CA-GEN-3:** El promedio de visitantes de días con `precip_mm ≥ 25` es menor que el de días con `precip_mm < 2`.
- **CA-GEN-4:** El promedio de sábados + domingos es mayor que el de martes + miércoles.
- **CA-GEN-5:** Ningún valor es negativo ni supera `capacidad_diaria`.
- **CA-GEN-6:** Todas las filas tienen `synthetic = 1`.

> **Orden de magnitud esperado** (simulación de referencia con la config por defecto, 3 años):
> `base_diaria` ≈ 380; ≈ 250 visitantes un martes/miércoles vs ≈ 520 un fin de semana;
> ≈ 180 en días de lluvia ≥ 25 mm vs ≈ 430 en días secos; percentiles P25 ≈ 220, P75 ≈ 415, P95 ≈ 730.
> Los valores exactos dependen del orden en que se consuma el generador aleatorio; si la
> implementación se aleja mucho de estos rangos, revisar la lógica antes que los tests.

## 5. ADR-02 · SQLite en lugar de RDS/DynamoDB

- **Contexto:** ~1 100 filas de histórico + caché de clima; una sola instancia EC2.
- **Decisión:** SQLite en el volumen Docker `cueva-data`.
- **Consecuencias:** costo cero y cero configuración extra en AWS. Si se escala a varias instancias, migrar a RDS PostgreSQL (el acceso a datos va detrás de un repositorio `VisitsRepository` para que el cambio sea local).

## 6. Consecuencias y riesgos

| Riesgo | Mitigación |
|--------|-----------|
| Los números no son reales. | La API devuelve `"datos_sinteticos": true` y la UI muestra la leyenda (P4). |
| `proporcion_cueva` es un supuesto. | Está en config y documentado; cambiarlo recalibra todo. |
| La cifra de 160 000 cambia cada año. | Parámetro en config; basta regenerar con `--force`. |
