# 01 · Especificación de producto

## 1. Problema

Los operadores turísticos, guardaparques del SERNANP y vendedores de la zona de
la Cueva de las Lechuzas no tienen forma de anticipar cuánta gente llegará en los
próximos días. El clima de Tingo María (selva alta, época de lluvias de octubre a
abril) cambia mucho la afluencia: un día de tormenta vacía el lugar y un feriado
soleado lo llena.

## 2. Objetivo

Una app web que, para **hoy y los próximos 2 días**, muestre:

1. el pronóstico del clima en la cueva (desde WeatherAPI.com),
2. el **número estimado de visitantes**, con un rango y un nivel de afluencia,
3. **por qué** se estima ese número (factores).

> **Límite de 3 días:** el plan gratuito de WeatherAPI.com entrega pronóstico de
> hasta 3 días. Es una restricción, no un bug (ver `05-integracion-weatherapi.md`).

## 3. Usuarios (personas)

| Persona | Necesidad | Uso típico |
|---------|-----------|------------|
| **Guardaparque** (SERNANP) | Saber si necesitará más personal en el control de ingreso. | Revisa la app la tarde anterior. |
| **Operador turístico** (agencia en Tingo María) | Decidir si programa el tour a la cueva o lo cambia de día. | Consulta los 3 días. |
| **Turista** | Evitar llegar con lluvia fuerte o con mucha gente. | Abre la app desde el celular. |
| **Docente evaluador** | Verificar que la app funciona en AWS y que las specs se cumplen. | Abre la URL pública y revisa `/docs`. |

## 4. Alcance

**Incluye (MVP):**
- Predicción diaria para hoy, mañana y pasado mañana.
- Clima actual en la cueva.
- Histórico sintético de visitas (últimos 3 años) con gráfico.
- Endpoint de salud para el despliegue.
- Despliegue automático a EC2 al hacer push a `main`.

**No incluye:**
- Venta de entradas o reservas.
- Predicción por hora.
- Autenticación de usuarios (la app es pública y de solo lectura).
- Datos reales de ingreso diario del SERNANP (no existen públicamente, ver ADR-01).

## 5. Historias de usuario y criterios de aceptación

### HU-01 · Ver la predicción de hoy
**Como** turista **quiero** ver cuántas personas se esperan hoy en la cueva **para** decidir si voy.

```gherkin
Escenario: Predicción de hoy con clima normal
  Dado que WeatherAPI responde el pronóstico para las coordenadas de la cueva
  Cuando abro la página principal
  Entonces veo una tarjeta "Hoy" con la fecha en formato "vie 25 sep 2026"
  Y veo un número entero de visitantes estimados mayor o igual a 0
  Y veo un rango "entre X y Y personas" donde X ≤ estimado ≤ Y
  Y veo un nivel de afluencia: "Baja", "Media", "Alta" o "Muy alta"
  Y veo el ícono y texto de la condición del clima

Escenario: WeatherAPI no responde
  Dado que WeatherAPI devuelve error o supera 5 s de espera
  Cuando abro la página principal
  Entonces veo el mensaje "No pudimos obtener el clima. Mostramos una estimación solo con calendario."
  Y la predicción se calcula con factor_clima = 1.0
  Y la respuesta de la API incluye "clima_disponible": false
```

### HU-02 · Ver los próximos 3 días
**Como** operador turístico **quiero** comparar hoy, mañana y pasado mañana **para** elegir el mejor día del tour.

```gherkin
Escenario: Tres días de pronóstico
  Cuando abro la página principal
  Entonces veo exactamente 3 tarjetas ordenadas por fecha ascendente
  Y la primera corresponde a la fecha actual en America/Lima

Escenario: Fecha fuera de rango
  Cuando pido GET /api/v1/predicciones?fecha=<hoy+5>
  Entonces recibo HTTP 422
  Y el cuerpo contiene el código "FECHA_FUERA_DE_RANGO"
```

### HU-03 · Entender por qué
**Como** guardaparque **quiero** ver qué factores subieron o bajaron la estimación **para** confiar en ella.

```gherkin
Escenario: Desglose de factores
  Cuando despliego "¿Por qué este número?" en una tarjeta
  Entonces veo la base diaria y cada factor (temporada, día de semana, feriado, clima)
  Y cada factor muestra su valor (ej. "× 0.65") y una razón en texto (ej. "Lluvia fuerte: 18 mm")
  Y el producto de base × factores, redondeado, es igual al número estimado (salvo el tope de capacidad)
```

### HU-04 · Ver el histórico
**Como** docente evaluador **quiero** ver el histórico usado por el modelo **para** entender de dónde salen los números.

```gherkin
Escenario: Gráfico de histórico sintético
  Cuando entro a la sección "Histórico"
  Entonces veo un gráfico de visitantes por mes de los últimos 36 meses
  Y veo la leyenda "Datos sintéticos generados para fines académicos"
```

### HU-05 · Saber si el servicio está vivo
**Como** pipeline de despliegue **quiero** un endpoint de salud **para** verificar que el deploy funcionó.

```gherkin
Escenario: Health check
  Cuando llamo GET /api/v1/health
  Entonces recibo HTTP 200 con {"status": "ok", "version": "<sha corto del commit>"}
  Y la respuesta tarda menos de 300 ms
  Y no llama a WeatherAPI
```

## 6. Requisitos funcionales

| ID | Requisito | HU |
|----|-----------|----|
| RF-01 | El sistema consulta el pronóstico de WeatherAPI para las coordenadas `-9.3292,-76.0269`. | HU-01, HU-02 |
| RF-02 | El sistema calcula visitantes estimados con el modelo de `03-modelo-prediccion.md`. | HU-01 |
| RF-03 | Cada predicción incluye rango (mín, máx) y nivel de afluencia. | HU-01 |
| RF-04 | Cada predicción incluye el desglose de factores con valor y razón. | HU-03 |
| RF-05 | Solo se aceptan fechas desde hoy hasta hoy + 2 (America/Lima). | HU-02 |
| RF-06 | Si WeatherAPI falla, se predice con `factor_clima = 1.0` y se marca `clima_disponible=false`. | HU-01 |
| RF-07 | El sistema genera y persiste un dataset sintético de 3 años al arrancar si no existe. | HU-04 |
| RF-08 | El sistema expone el histórico agregado por mes. | HU-04 |
| RF-09 | El sistema expone `/api/v1/health` con la versión desplegada. | HU-05 |
| RF-10 | La UI muestra la atribución "Powered by WeatherAPI.com" con enlace (condición del plan gratuito). | — |
| RF-11 | Si el pronóstico trae alertas o lluvia ≥ 50 mm, la predicción incluye una advertencia de seguridad. | HU-01 |
