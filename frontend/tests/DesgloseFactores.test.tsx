import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DesgloseFactores } from '../src/components/DesgloseFactores'
import type { Prediccion } from '../src/api/client'

// Ejemplo tomado de specs/04-api.md §2 (GET /predicciones?fecha=2026-07-18).
const FACTORES_EJEMPLO: Prediccion['factores'] = {
  base_diaria: 350,
  temporada: { valor: 1.2, razon: 'Julio: vacaciones de medio año' },
  dia_semana: { valor: 1.45, razon: 'Sábado' },
  feriado: { valor: 1.0, razon: 'Día normal' },
  clima: { valor: 0.7, razon: 'Lluvia 12.0 mm (10–25 mm)' },
  tope_capacidad_aplicado: false,
}

// HU-03 (specs/01-producto.md §5): al desplegar "¿Por qué este número?" se
// ven la base diaria y los 4 factores, cada uno con su valor (ej. "× 0.65")
// y una razón en texto.
describe('DesgloseFactores', () => {
  it('está cerrado por defecto (open=false en <details>)', () => {
    const { container } = render(<DesgloseFactores factores={FACTORES_EJEMPLO} />)
    const details = container.querySelector('details')
    expect(details).not.toBeNull()
    expect(details).not.toHaveAttribute('open')
  })

  it('el <summary> dice "¿Por qué este número?"', () => {
    render(<DesgloseFactores factores={FACTORES_EJEMPLO} />)
    expect(screen.getByText('¿Por qué este número?')).toBeInTheDocument()
  })

  it('muestra la base diaria y el valor + razón de cada uno de los 4 factores', () => {
    render(<DesgloseFactores factores={FACTORES_EJEMPLO} />)

    expect(screen.getByText(/base diaria: 350/i)).toBeInTheDocument()

    expect(screen.getByText(/× 1\.20/)).toBeInTheDocument()
    expect(screen.getByText(/julio: vacaciones de medio año/i)).toBeInTheDocument()

    expect(screen.getByText(/× 1\.45/)).toBeInTheDocument()
    expect(screen.getByText(/sábado/i)).toBeInTheDocument()

    expect(screen.getByText(/× 1\.00/)).toBeInTheDocument()
    expect(screen.getByText(/día normal/i)).toBeInTheDocument()

    expect(screen.getByText(/× 0\.70/)).toBeInTheDocument()
    expect(screen.getByText(/lluvia 12\.0 mm/i)).toBeInTheDocument()
  })

  it('avisa cuando se aplicó el tope de capacidad', () => {
    render(
      <DesgloseFactores
        factores={{ ...FACTORES_EJEMPLO, tope_capacidad_aplicado: true }}
      />,
    )
    expect(screen.getByText(/tope de capacidad/i)).toBeInTheDocument()
  })

  it('no muestra el aviso de tope cuando no se aplicó', () => {
    render(<DesgloseFactores factores={FACTORES_EJEMPLO} />)
    expect(screen.queryByText(/tope de capacidad/i)).not.toBeInTheDocument()
  })
})
