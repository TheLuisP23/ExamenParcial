import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { GraficoHistorico } from '../src/components/GraficoHistorico'
import type { HistoricoMensual } from '../src/api/client'
import * as apiClient from '../src/api/client'

// FE-04 (specs/06-frontend.md §2, fila `GraficoHistorico`, HU-04): consume su
// propio endpoint `/historico/mensual` (mismo patrón que `Encabezado`/
// `PiePagina`), así que se mockea `getHistoricoMensual` para controlar la
// serie de ejemplo sin depender de la red.
//
// Nota sobre Recharts + JSDOM: `ResponsiveContainer` necesita `ResizeObserver`
// y un `getBoundingClientRect()` con tamaño positivo para renderizar el
// gráfico; ambos se mockean globalmente en `tests/setup.ts` (ver el
// comentario ahí para el detalle del gotcha).
const SERIE_EJEMPLO: HistoricoMensual = {
  datos_sinteticos: true,
  serie: [
    { mes: '2026-07', visitantes: 9800, promedio_diario: 316 },
    { mes: '2026-08', visitantes: 10200, promedio_diario: 329 },
    { mes: '2026-09', visitantes: 11500, promedio_diario: 383 },
  ],
}

describe('GraficoHistorico', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('muestra el encabezado de la sección y la leyenda de datos sintéticos siempre, incluso mientras carga', () => {
    vi.spyOn(apiClient, 'getHistoricoMensual').mockReturnValue(new Promise(() => {}))

    render(<GraficoHistorico />)

    expect(screen.getByRole('heading', { name: 'Histórico' })).toBeInTheDocument()
    // HU-04 (specs/01-producto.md §5): texto exacto, sin parafrasear, porque
    // una prueba E2E futura (E2E-02) busca esta subcadena literal.
    expect(screen.getByText('Datos sintéticos generados para fines académicos')).toBeInTheDocument()
  })

  it('pide 36 meses por defecto a /historico/mensual', () => {
    vi.spyOn(apiClient, 'getHistoricoMensual').mockReturnValue(new Promise(() => {}))

    render(<GraficoHistorico />)

    expect(apiClient.getHistoricoMensual).toHaveBeenCalledWith(36)
  })

  it('renderiza una barra por cada mes de la serie cuando /historico/mensual responde 200', async () => {
    vi.spyOn(apiClient, 'getHistoricoMensual').mockResolvedValue(SERIE_EJEMPLO)

    const { container } = render(<GraficoHistorico />)

    await waitFor(() => {
      expect(container.querySelectorAll('.recharts-bar-rectangle')).toHaveLength(SERIE_EJEMPLO.serie.length)
    })

    // Eje Y con la etiqueta "visitantes/mes" exigida por specs/06-frontend.md §2.
    expect(screen.getByText('visitantes/mes')).toBeInTheDocument()
  })

  it('muestra un mensaje de error sin romper la sección si /historico/mensual falla', async () => {
    vi.spyOn(apiClient, 'getHistoricoMensual').mockRejectedValue(new Error('network error'))

    render(<GraficoHistorico />)

    expect(await screen.findByText(/no pudimos cargar el histórico/i)).toBeInTheDocument()
    // La leyenda de datos sintéticos y el encabezado siguen presentes.
    expect(screen.getByRole('heading', { name: 'Histórico' })).toBeInTheDocument()
    expect(screen.getByText('Datos sintéticos generados para fines académicos')).toBeInTheDocument()
  })
})
