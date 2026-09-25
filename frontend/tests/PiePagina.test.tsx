import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PiePagina } from '../src/components/PiePagina'
import type { Health } from '../src/api/client'
import * as apiClient from '../src/api/client'

// FE-03 (specs/06-frontend.md §2, fila `PiePagina`, RF-10): consume su
// propio endpoint `/health`, así que se mockea `getHealth` para controlar la
// versión mostrada sin depender de la red.
describe('PiePagina', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('RF-10: incluye el enlace de atribución con el href exacto de WeatherAPI', () => {
    vi.spyOn(apiClient, 'getHealth').mockReturnValue(new Promise(() => {}))

    render(<PiePagina />)

    const enlace = screen.getByRole('link', { name: /powered by weatherapi\.com/i })
    expect(enlace).toHaveAttribute('href', 'https://www.weatherapi.com/')
  })

  it('muestra la versión real que devuelve /health (no un valor fijo)', async () => {
    const health: Health = { status: 'ok', version: 'a1b2c3d' }
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue(health)

    render(<PiePagina />)

    expect(await screen.findByText(/versión a1b2c3d/i)).toBeInTheDocument()
  })

  it('mantiene el mensaje de datos sintéticos (RNF-14) y no rompe si /health falla', async () => {
    vi.spyOn(apiClient, 'getHealth').mockRejectedValue(new Error('network error'))

    render(<PiePagina />)

    expect(screen.getByText(/datos sintéticos con fines académicos/i)).toBeInTheDocument()
    // El enlace de atribución sigue presente aunque /health falle.
    expect(
      screen.getByRole('link', { name: /powered by weatherapi\.com/i }),
    ).toHaveAttribute('href', 'https://www.weatherapi.com/')

    await waitFor(() => {
      expect(screen.queryByText(/versión/i)).not.toBeInTheDocument()
    })
  })
})
