import { useEffect, useState } from 'react'
import type { Prediccion } from './api/client'
import { getPredicciones } from './api/client'
import { Advertencias } from './components/Advertencias'
import { Encabezado } from './components/Encabezado'
import { EsqueletoTarjetaDia } from './components/EsqueletoTarjetaDia'
import { GraficoHistorico } from './components/GraficoHistorico'
import { PiePagina } from './components/PiePagina'
import { TarjetaDia } from './components/TarjetaDia'

/** Número de `TarjetaDia` que muestra la pantalla (hoy, mañana, pasado mañana; RF-01..05). */
const NUM_TARJETAS = 3

/**
 * Shell de la SPA (FE-01..FE-05, specs/06-frontend.md §5).
 * `Encabezado`, `PiePagina` (FE-03) y `GraficoHistorico` (FE-04) consumen
 * sus propios endpoints y manejan su propio estado de carga/éxito/error.
 * `TarjetaDia`/`Advertencias` en cambio siguen recibiendo props ya
 * resueltas (specs/06-frontend.md §2), así que es este componente el que
 * cablea el fetch real a `GET /predicciones` (FE-05, RNF-13) y decide qué
 * mostrar en cada uno de los 3 estados de specs/06-frontend.md §3:
 * cargando (esqueletos), éxito (las 3 tarjetas con datos reales,
 * `clima_disponible=false` ya resuelto por `TarjetaDia`/FE-02) y error de
 * red/5xx (mensaje + botón "Reintentar").
 */
function App() {
  const [predicciones, setPredicciones] = useState<Prediccion[] | null>(null)
  const [error, setError] = useState(false)
  // Incrementar este contador es lo que dispara un nuevo intento: el botón
  // "Reintentar" solo lo incrementa, y el `useEffect` de abajo, al depender
  // de él, vuelve a llamar a `getPredicciones()`.
  const [intento, setIntento] = useState(0)

  useEffect(() => {
    let cancelado = false

    setError(false)
    setPredicciones(null)

    getPredicciones()
      .then((respuesta) => {
        if (!cancelado) setPredicciones(respuesta.predicciones)
      })
      .catch(() => {
        if (!cancelado) setError(true)
      })

    return () => {
      cancelado = true
    }
  }, [intento])

  return (
    <main>
      <Encabezado />

      <section aria-label="Predicción de visitantes para los próximos 3 días" className="tarjetas-dia">
        {predicciones
          ? predicciones.map((prediccion, index) => (
              <TarjetaDia key={prediccion.fecha} prediccion={prediccion} index={index} />
            ))
          : !error
            ? Array.from({ length: NUM_TARJETAS }, (_, index) => <EsqueletoTarjetaDia key={index} />)
            : null}
      </section>

      {error ? (
        <div role="alert" className="predicciones-error">
          <p>No pudimos calcular la predicción. Reintenta en unos minutos.</p>
          <button type="button" onClick={() => setIntento((n) => n + 1)}>
            Reintentar
          </button>
        </div>
      ) : null}

      {predicciones ? <Advertencias predicciones={predicciones} /> : null}

      <GraficoHistorico />

      <PiePagina />
    </main>
  )
}

export default App
