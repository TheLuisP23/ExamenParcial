import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Advertencias } from '../src/components/Advertencias'
import type { Prediccion } from '../src/api/client'

function prediccionBase(overrides: Partial<Prediccion>): Prediccion {
  return {
    fecha: '2026-09-25',
    visitantes_estimados: 100,
    rango: { min: 80, max: 120 },
    nivel_afluencia: 'Media',
    clima_disponible: true,
    clima: null,
    factores: {
      base_diaria: 350,
      temporada: { valor: 1, razon: 'x' },
      dia_semana: { valor: 1, razon: 'x' },
      feriado: { valor: 1, razon: 'x' },
      clima: { valor: 1, razon: 'x' },
      tope_capacidad_aplicado: false,
    },
    advertencias: [],
    ...overrides,
  }
}

// specs/06-frontend.md §2: "Banda con role='alert'; una línea por
// advertencia con la fecha." Recibe predicciones[] de los 3 días (elección
// de props documentada en el propio componente).
describe('Advertencias', () => {
  it('no renderiza nada si ninguna predicción trae advertencias', () => {
    const predicciones = [prediccionBase({ fecha: '2026-09-25' }), prediccionBase({ fecha: '2026-09-26' })]
    const { container } = render(<Advertencias predicciones={predicciones} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renderiza una banda con role="alert" cuando hay advertencias', () => {
    const predicciones = [
      prediccionBase({
        fecha: '2026-09-27',
        advertencias: [{ codigo: 'TORMENTA', mensaje: 'Tormenta eléctrica pronosticada en horario de visita.' }],
      }),
    ]
    render(<Advertencias predicciones={predicciones} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('muestra una línea por advertencia, incluyendo la fecha a la que corresponde', () => {
    const predicciones = [
      prediccionBase({
        fecha: '2026-09-25',
        advertencias: [{ codigo: 'LLUVIA_EXTREMA', mensaje: 'Lluvia extrema prevista: 60 mm.' }],
      }),
      prediccionBase({
        fecha: '2026-09-27',
        advertencias: [{ codigo: 'TORMENTA', mensaje: 'Tormenta eléctrica pronosticada en horario de visita.' }],
      }),
    ]
    render(<Advertencias predicciones={predicciones} />)

    const alerta = screen.getByRole('alert')
    expect(alerta).toHaveTextContent('vie 25 sep 2026')
    expect(alerta).toHaveTextContent('Lluvia extrema prevista: 60 mm.')
    expect(alerta).toHaveTextContent('dom 27 sep 2026')
    expect(alerta).toHaveTextContent('Tormenta eléctrica pronosticada en horario de visita.')
  })

  it('usa advertencia.mensaje tal cual viene del backend, sin inventar texto', () => {
    const mensajeBackend = 'Mensaje literal de prueba desde el backend.'
    const predicciones = [
      prediccionBase({
        fecha: '2026-09-25',
        advertencias: [{ codigo: 'ALERTA_OFICIAL', mensaje: mensajeBackend }],
      }),
    ]
    render(<Advertencias predicciones={predicciones} />)
    expect(screen.getByText(new RegExp(mensajeBackend))).toBeInTheDocument()
  })
})
