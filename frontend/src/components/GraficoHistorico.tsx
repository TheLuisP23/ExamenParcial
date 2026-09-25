import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getHistoricoMensual, type HistoricoMensual } from '../api/client'
import { formatMesCorto, formatMiles } from '../utils/formato'

/**
 * Sección "Histórico" de la SPA (FE-04, specs/06-frontend.md §1-§2, HU-04).
 *
 * Igual que `Encabezado`/`PiePagina` (FE-03), consume su propio endpoint
 * (`GET /historico/mensual`) y maneja su propio estado local de carga/éxito/
 * error, en vez de recibir props resueltas por `App.tsx`. Por defecto pide
 * 36 meses (el default del backend también es 36, RF-08).
 *
 * La leyenda "Datos sintéticos generados para fines académicos" es el texto
 * literal exigido por HU-04 (specs/01-producto.md §5): una futura prueba E2E
 * (E2E-02) busca esa subcadena exacta, así que no se parafrasea. Se muestra
 * siempre (no depende de la respuesta de la API), reflejando la constante
 * `datos_sinteticos: true` del contrato.
 */
export function GraficoHistorico() {
  const [historico, setHistorico] = useState<HistoricoMensual | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelado = false

    getHistoricoMensual(36)
      .then((datos) => {
        if (!cancelado) {
          setHistorico(datos)
          setError(false)
        }
      })
      .catch(() => {
        if (!cancelado) {
          setHistorico(null)
          setError(true)
        }
      })

    return () => {
      cancelado = true
    }
  }, [])

  return (
    <section aria-label="Histórico" className="grafico-historico">
      <h2>Histórico</h2>
      <p className="grafico-historico__leyenda">Datos sintéticos generados para fines académicos</p>

      {error ? (
        <p>No pudimos cargar el histórico. Reintenta en unos minutos.</p>
      ) : historico ? (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={historico.serie} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="mes" tickFormatter={formatMesCorto} tick={{ fontSize: 11 }} interval="preserveStartEnd" />
            <YAxis
              label={{ value: 'visitantes/mes', angle: -90, position: 'insideLeft' }}
              tickFormatter={(valor: number) => formatMiles(valor)}
              width={70}
            />
            <Tooltip
              labelFormatter={(mes) => (typeof mes === 'string' ? formatMesCorto(mes) : mes)}
              formatter={(valor) => [typeof valor === 'number' ? formatMiles(valor) : valor, 'Visitantes']}
            />
            <Bar dataKey="visitantes" fill="#1d4ed8" name="Visitantes" />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <p aria-hidden="true">Cargando histórico…</p>
      )}
    </section>
  )
}
