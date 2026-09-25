import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TarjetaDia } from '../src/components/TarjetaDia'
import type { Prediccion } from '../src/api/client'

const PREDICCION_CON_CLIMA: Prediccion = {
  fecha: '2026-09-25',
  visitantes_estimados: 426,
  rango: { min: 341, max: 511 },
  nivel_afluencia: 'Alta',
  clima_disponible: true,
  clima: {
    condicion: 'Lluvia moderada',
    codigo_condicion: 1189,
    icono_url: 'https://cdn.weatherapi.com/weather/64x64/day/302.png',
    temp_max_c: 29.0,
    temp_min_c: 21.4,
    precipitacion_mm: 12.0,
    probabilidad_lluvia: 60,
  },
  factores: {
    base_diaria: 350,
    temporada: { valor: 1.2, razon: 'Julio: vacaciones de medio año' },
    dia_semana: { valor: 1.45, razon: 'Sábado' },
    feriado: { valor: 1.0, razon: 'Día normal' },
    clima: { valor: 0.7, razon: 'Lluvia 12.0 mm (10–25 mm)' },
    tope_capacidad_aplicado: false,
  },
  advertencias: [],
}

const PREDICCION_SIN_CLIMA: Prediccion = {
  ...PREDICCION_CON_CLIMA,
  fecha: '2026-09-27',
  clima_disponible: false,
  clima: null,
}

// HU-01 (specs/01-producto.md §5): tarjeta "Hoy" con fecha
// "vie 25 sep 2026", número entero >= 0, rango "entre X y Y personas" con
// X <= estimado <= Y, nivel de afluencia y clima con ícono+texto.
describe('TarjetaDia', () => {
  it('index 0: título "Hoy" y fecha completa "vie 25 sep 2026"', () => {
    render(<TarjetaDia prediccion={PREDICCION_CON_CLIMA} index={0} />)
    expect(screen.getByRole('heading', { name: 'Hoy' })).toBeInTheDocument()
    expect(screen.getByText('vie 25 sep 2026')).toBeInTheDocument()
  })

  it('index 1: título "Mañana"', () => {
    render(<TarjetaDia prediccion={{ ...PREDICCION_CON_CLIMA, fecha: '2026-09-26' }} index={1} />)
    expect(screen.getByRole('heading', { name: 'Mañana' })).toBeInTheDocument()
  })

  it('index 2: título con el día abreviado y número', () => {
    render(<TarjetaDia prediccion={PREDICCION_SIN_CLIMA} index={2} />)
    expect(screen.getByRole('heading', { name: 'Dom 27' })).toBeInTheDocument()
  })

  it('muestra el número de visitantes con separador de miles', () => {
    render(<TarjetaDia prediccion={PREDICCION_CON_CLIMA} index={0} />)
    expect(screen.getByText('426')).toBeInTheDocument()
  })

  it('muestra el rango como "entre X y Y personas"', () => {
    render(<TarjetaDia prediccion={PREDICCION_CON_CLIMA} index={0} />)
    expect(screen.getByText('entre 341 y 511 personas')).toBeInTheDocument()
  })

  it('muestra el nivel de afluencia', () => {
    render(<TarjetaDia prediccion={PREDICCION_CON_CLIMA} index={0} />)
    expect(screen.getByText('Alta')).toBeInTheDocument()
  })

  it('clima_disponible=true: muestra ícono con alt=condición y el texto de la condición', () => {
    render(<TarjetaDia prediccion={PREDICCION_CON_CLIMA} index={0} />)
    const img = screen.getByRole('img', { name: 'Lluvia moderada' })
    expect(img).toHaveAttribute('src', PREDICCION_CON_CLIMA.clima?.icono_url)
    expect(screen.getByText('Lluvia moderada')).toBeInTheDocument()
  })

  it('clima_disponible=false: muestra "Estimación solo con calendario" y no el ícono de clima', () => {
    render(<TarjetaDia prediccion={PREDICCION_SIN_CLIMA} index={2} />)
    expect(screen.getByText('Estimación solo con calendario')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('incluye el desglose de factores cerrado por defecto', () => {
    render(<TarjetaDia prediccion={PREDICCION_CON_CLIMA} index={0} />)
    const details = screen.getByText('¿Por qué este número?').closest('details')
    expect(details).not.toHaveAttribute('open')
  })
})
