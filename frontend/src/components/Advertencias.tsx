import type { Prediccion } from '../api/client'
import { formatFechaCorta } from '../utils/formato'

export interface AdvertenciasProps {
  /**
   * Elección de forma de props (documentada para FE-02): este componente
   * recibe `predicciones[]` completo, no un array ya aplanado de
   * `{fecha, advertencia}`. Así el emparejamiento fecha↔advertencia vive en
   * un solo lugar (aquí) en vez de duplicarse en cada consumidor (p. ej.
   * `App.tsx`), y el componente sigue reflejando 1:1 la forma de
   * `PrediccionesResponse.predicciones` del contrato.
   */
  predicciones: Prediccion[]
}

/**
 * Banda de advertencias de los 3 días (specs/06-frontend.md §2, HU-01).
 * `role="alert"` para que un lector de pantalla la anuncie; una línea por
 * advertencia, incluyendo la fecha a la que corresponde. El texto es
 * `advertencia.mensaje` tal cual lo entrega el backend (ya en español), sin
 * inventar redacciones nuevas.
 */
export function Advertencias({ predicciones }: AdvertenciasProps) {
  const items = predicciones.flatMap((prediccion) =>
    prediccion.advertencias.map((advertencia) => ({
      fecha: prediccion.fecha,
      advertencia,
    })),
  )

  if (items.length === 0) {
    return null
  }

  return (
    <div role="alert" className="advertencias">
      <ul>
        {items.map(({ fecha, advertencia }) => (
          <li key={`${fecha}-${advertencia.codigo}`}>
            <strong>{formatFechaCorta(fecha)}:</strong> {advertencia.mensaje}
          </li>
        ))}
      </ul>
    </div>
  )
}
