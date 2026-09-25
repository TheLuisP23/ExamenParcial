/**
 * Utilidades de formato en español (es-PE) para las tarjetas de predicción
 * (FE-02, HU-01/02/03, specs/06-frontend.md §2).
 *
 * No usamos `Intl.DateTimeFormat('es-PE', …)` directamente para la fecha
 * corta: en este entorno (Node 20, ICU embebido) y en varios navegadores
 * recientes el CLDR de `es-PE` devuelve `"vie, 25 set. 2026"` (con coma y
 * "set." abreviado a 4 letras con punto), que **no** coincide con el
 * formato exacto exigido por HU-01 (specs/01-producto.md §5):
 * `"vie 25 sep 2026"` (sin coma, sin puntos, abreviaturas de 3 letras).
 * Se verificó con:
 *   new Intl.DateTimeFormat('es-PE', {weekday:'short', day:'numeric',
 *     month:'short', year:'numeric'}).format(new Date(2026,8,25))
 *   → "vie, 25 set. 2026"
 * Por eso armamos el string a mano con tablas fijas, para garantizar el
 * formato exacto en cualquier entorno (Node de los tests, cualquier
 * navegador de producción).
 */

const DIAS_ABREV = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'] as const

const MESES_ABREV = [
  'ene',
  'feb',
  'mar',
  'abr',
  'may',
  'jun',
  'jul',
  'ago',
  'sep',
  'oct',
  'nov',
  'dic',
] as const

/**
 * Parsea una fecha `"YYYY-MM-DD"` (formato del contrato, ver `Prediccion.fecha`
 * en openapi.yaml) como fecha **local**, evitando el corrimiento de un día
 * que produce `new Date("YYYY-MM-DD")` al interpretarla como medianoche UTC
 * en zonas horarias con offset negativo (p. ej. America/Lima, UTC-5).
 */
export function parseFechaLocal(fecha: string): Date {
  const [anio, mes, dia] = fecha.split('-').map(Number)
  return new Date(anio, mes - 1, dia)
}

/** Fecha completa en el formato literal exigido por HU-01: `"vie 25 sep 2026"`. */
export function formatFechaCorta(fecha: string): string {
  const d = parseFechaLocal(fecha)
  return `${DIAS_ABREV[d.getDay()]} ${d.getDate()} ${MESES_ABREV[d.getMonth()]} ${d.getFullYear()}`
}

/** Día abreviado capitalizado + número de día, p. ej. `"Dom 27"` (3ª tarjeta). */
export function formatDiaAbreviadoConNumero(fecha: string): string {
  const d = parseFechaLocal(fecha)
  const dia = DIAS_ABREV[d.getDay()]
  return `${dia.charAt(0).toUpperCase()}${dia.slice(1)} ${d.getDate()}`
}

/**
 * Entero con separador de miles usando un espacio simple (p. ej. `"1 024"`,
 * ver mockup de specs/06-frontend.md §2). No se delega en
 * `Intl.NumberFormat('es-PE')`: en este entorno esa combinación produce
 * `"1,024"` (coma) en vez del espacio del mockup, así que se agrupa a mano
 * para que el separador sea estable sin importar el ICU del entorno.
 */
export function formatMiles(valor: number): string {
  const entero = Math.round(valor)
  return entero.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
}

/**
 * Título de una `TarjetaDia` según su posición entre las 3 predicciones que
 * entrega `/predicciones` (HU-02: el backend ya las devuelve ordenadas por
 * fecha ascendente y la primera es "hoy" en America/Lima; este componente no
 * reordena nada, solo confía en el índice recibido).
 */
export function tituloTarjeta(fecha: string, index: number): string {
  if (index === 0) return 'Hoy'
  if (index === 1) return 'Mañana'
  return formatDiaAbreviadoConNumero(fecha)
}

/**
 * Etiqueta corta de un mes del histórico (FE-04, `HistoricoMensual.serie[].mes`,
 * formato del contrato `"YYYY-MM"`) para el eje X de `GraficoHistorico`, p. ej.
 * `"sep 24"`. Con hasta 36 barras en pantalla, mostrar el mes completo con año
 * de 4 dígitos (`"septiembre 2024"`) desbordaría el eje, así que se usa la
 * misma tabla de abreviaturas de 3 letras que `formatFechaCorta` más los
 * últimos 2 dígitos del año.
 */
export function formatMesCorto(mes: string): string {
  const [anio, mesNum] = mes.split('-').map(Number)
  return `${MESES_ABREV[mesNum - 1]} ${anio.toString().slice(-2)}`
}
