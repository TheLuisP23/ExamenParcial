import { describe, expect, it } from 'vitest'
import {
  formatDiaAbreviadoConNumero,
  formatFechaCorta,
  formatMiles,
  parseFechaLocal,
  tituloTarjeta,
} from '../src/utils/formato'

// HU-01 (specs/01-producto.md §5): "veo una tarjeta 'Hoy' con la fecha en
// formato 'vie 25 sep 2026'". Verificación carácter por carácter: viernes 25
// de septiembre de 2026 debe producir exactamente ese string, sin coma y sin
// puntos en la abreviatura del mes (a diferencia de lo que da
// Intl.DateTimeFormat('es-PE', …) en este entorno: "vie, 25 set. 2026").
describe('formatFechaCorta', () => {
  it('produce exactamente "vie 25 sep 2026" para el viernes 25 de septiembre de 2026', () => {
    expect(formatFechaCorta('2026-09-25')).toBe('vie 25 sep 2026')
  })

  it('no tiene coma ni puntos, y usa abreviaturas de 3 letras', () => {
    const resultado = formatFechaCorta('2026-09-25')
    expect(resultado).not.toContain(',')
    expect(resultado).not.toContain('.')
  })

  it('formatea correctamente otro día de otro mes (sábado 1 de enero de 2028)', () => {
    expect(formatFechaCorta('2028-01-01')).toBe('sáb 1 ene 2028')
  })
})

describe('parseFechaLocal', () => {
  it('interpreta "YYYY-MM-DD" como fecha local, no UTC (evita corrimiento de día)', () => {
    const d = parseFechaLocal('2026-09-25')
    expect(d.getFullYear()).toBe(2026)
    expect(d.getMonth()).toBe(8) // 0-indexado: setiembre
    expect(d.getDate()).toBe(25)
  })
})

describe('formatDiaAbreviadoConNumero', () => {
  it('produce "Dom 27" para domingo 27 de setiembre de 2026', () => {
    expect(formatDiaAbreviadoConNumero('2026-09-27')).toBe('Dom 27')
  })
})

describe('formatMiles', () => {
  it('agrupa miles con espacio simple: 1024 -> "1 024"', () => {
    expect(formatMiles(1024)).toBe('1 024')
  })

  it('no agrupa números menores a 1000', () => {
    expect(formatMiles(426)).toBe('426')
  })

  it('redondea decimales antes de formatear', () => {
    expect(formatMiles(1023.6)).toBe('1 024')
  })
})

describe('tituloTarjeta (HU-02: orden hoy/mañana/pasado mañana)', () => {
  it('index 0 es siempre "Hoy"', () => {
    expect(tituloTarjeta('2026-09-25', 0)).toBe('Hoy')
  })

  it('index 1 es siempre "Mañana"', () => {
    expect(tituloTarjeta('2026-09-26', 1)).toBe('Mañana')
  })

  it('index 2 usa el día abreviado con número', () => {
    expect(tituloTarjeta('2026-09-27', 2)).toBe('Dom 27')
  })
})
