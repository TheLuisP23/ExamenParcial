import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Encabezado } from '../src/components/Encabezado'
import { PredictorApiError, type ClimaActual } from '../src/api/client'
import * as apiClient from '../src/api/client'

// FE-03 (specs/06-frontend.md §2, fila `Encabezado`): consume su propio
// endpoint `/clima/actual`, así que se mockea `getClimaActual` (no `fetch`
// directamente) para controlar el caso de éxito y el de error 503 sin
// depender de la red.
describe('Encabezado', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('muestra el título y la ubicación siempre, incluso mientras carga', () => {
    vi.spyOn(apiClient, 'getClimaActual').mockReturnValue(new Promise(() => {}))

    render(<Encabezado />)

    expect(
      screen.getByRole('heading', { name: /cueva de las lechuzas/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/pn tingo maría, huánuco/i)).toBeInTheDocument()
  })

  it('muestra la línea de clima actual cuando /clima/actual responde 200', async () => {
    const clima: ClimaActual = {
      temp_c: 27.4,
      condicion: 'Parcialmente nublado',
      humedad: 80,
      actualizado_en: '2026-09-25T12:00:00-05:00',
    }
    vi.spyOn(apiClient, 'getClimaActual').mockResolvedValue(clima)

    render(<Encabezado />)

    expect(await screen.findByText(/clima ahora: 27 °c, parcialmente nublado/i)).toBeInTheDocument()
  })

  it('RF-06/specs §2: si /clima/actual responde 503, oculta la línea de clima sin romper la página', async () => {
    vi.spyOn(apiClient, 'getClimaActual').mockRejectedValue(
      new PredictorApiError('CLIMA_NO_DISPONIBLE', 'WeatherAPI no disponible y sin caché'),
    )

    render(<Encabezado />)

    // El título y el subtítulo de ubicación siguen ahí (la página no se rompe).
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /cueva de las lechuzas/i }),
      ).toBeInTheDocument()
    })
    expect(screen.getByText(/pn tingo maría, huánuco/i)).toBeInTheDocument()

    // ... pero sin la línea de "Clima ahora: ...".
    expect(screen.queryByText(/clima ahora/i)).not.toBeInTheDocument()
  })

  it('también oculta la línea de clima ante un error de red genérico (no solo 503)', async () => {
    vi.spyOn(apiClient, 'getClimaActual').mockRejectedValue(new TypeError('Failed to fetch'))

    render(<Encabezado />)

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /cueva de las lechuzas/i }),
      ).toBeInTheDocument()
    })
    expect(screen.queryByText(/clima ahora/i)).not.toBeInTheDocument()
  })
})
