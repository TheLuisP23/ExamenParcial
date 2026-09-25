import { useEffect, useState } from 'react'
import { getClimaActual, type ClimaActual } from '../api/client'

/**
 * Encabezado de la SPA (FE-03, specs/06-frontend.md §1-§2).
 *
 * A diferencia de `TarjetaDia` (que recibe props ya resueltas desde
 * `App.tsx`), este componente consume su propio endpoint
 * (`GET /clima/actual`) y maneja su propio estado local de carga/éxito/error,
 * tal como indica la tabla de componentes de specs/06-frontend.md §2.
 *
 * Regla crítica (specs/06-frontend.md §2, fila `Encabezado`): "Si responde
 * 503, ocultar la línea de clima actual (no romper la página)." Por eso
 * cualquier error (503 `CLIMA_NO_DISPONIBLE` u otro error de red) se traduce
 * simplemente en no mostrar esa línea, sin lanzar ni propagar la excepción:
 * el título y el subtítulo de ubicación siempre se renderizan.
 */
export function Encabezado() {
  const [clima, setClima] = useState<ClimaActual | null>(null)

  useEffect(() => {
    let cancelado = false

    getClimaActual()
      .then((datos) => {
        if (!cancelado) setClima(datos)
      })
      .catch(() => {
        // Ver regla crítica arriba: un error (503 u otro) solo implica no
        // mostrar la línea de clima actual, nunca romper el encabezado.
        if (!cancelado) setClima(null)
      })

    return () => {
      cancelado = true
    }
  }, [])

  return (
    <header>
      <h1>🦉 Cueva de las Lechuzas · ¿Cuánta gente irá?</h1>
      <p>
        PN Tingo María, Huánuco
        {clima ? ` · Clima ahora: ${Math.round(clima.temp_c)} °C, ${clima.condicion}` : null}
      </p>
    </header>
  )
}
