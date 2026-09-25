import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChipNivel } from '../src/components/ChipNivel'

// HU-01 (specs/01-producto.md §5): "veo un nivel de afluencia: 'Baja',
// 'Media', 'Alta' o 'Muy alta'". Accesibilidad (specs/06-frontend.md §2,
// front.md directriz 5): el color nunca es el único portador del
// significado, el texto de la etiqueta siempre está presente.
describe('ChipNivel', () => {
  it.each(['Baja', 'Media', 'Alta', 'Muy alta'] as const)(
    'muestra el texto visible de la etiqueta "%s"',
    (nivel) => {
      render(<ChipNivel nivel_afluencia={nivel} />)
      expect(screen.getByText(nivel)).toBeInTheDocument()
    },
  )

  it('usa un color de fondo distinto por nivel (no depende solo del texto)', () => {
    const { container: baja } = render(<ChipNivel nivel_afluencia="Baja" />)
    const { container: muyAlta } = render(<ChipNivel nivel_afluencia="Muy alta" />)

    const colorBaja = (baja.querySelector('.chip-nivel') as HTMLElement).style.backgroundColor
    const colorMuyAlta = (muyAlta.querySelector('.chip-nivel') as HTMLElement).style
      .backgroundColor

    expect(colorBaja).not.toBe('')
    expect(colorBaja).not.toBe(colorMuyAlta)
  })
})
