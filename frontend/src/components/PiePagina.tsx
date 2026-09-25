import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'

/**
 * Pie de página de la SPA (FE-03, specs/06-frontend.md §1-§2, RF-10).
 *
 * Igual que `Encabezado`, consume su propio endpoint (`GET /health`) y
 * maneja su propio estado local de carga/éxito/error, en vez de recibir
 * props resueltas por `App.tsx`.
 *
 * RF-10: siempre debe incluir el enlace de atribución a WeatherAPI.com con
 * `href="https://www.weatherapi.com/"` exacto (lo pide la futura prueba
 * FT-05), independientemente de si `/health` respondió o no. Lo que sí
 * depende de la respuesta de `/health` es la versión mostrada
 * (`health.version`, nunca un valor inventado): mientras no haya respuesta
 * o si la llamada falla, simplemente no se muestra ese dato, sin romper el
 * resto del pie.
 */
export function PiePagina() {
  const [version, setVersion] = useState<string | null>(null)

  useEffect(() => {
    let cancelado = false

    getHealth()
      .then((health) => {
        if (!cancelado) setVersion(health.version)
      })
      .catch(() => {
        if (!cancelado) setVersion(null)
      })

    return () => {
      cancelado = true
    }
  }, [])

  return (
    <footer>
      {/* Los datos de visitas son sintéticos (constitución P4 / RNF-14) */}
      <p>Horario 08:00–17:00 · Datos sintéticos con fines académicos.</p>
      <p>
        <a href="https://www.weatherapi.com/">Powered by WeatherAPI.com</a>
        {version ? ` · versión ${version}` : null}
      </p>
    </footer>
  )
}
