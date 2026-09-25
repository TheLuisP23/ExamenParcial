import type { Prediccion } from '../api/client'
import { ChipNivel } from './ChipNivel'
import { DesgloseFactores } from './DesgloseFactores'
import { formatFechaCorta, formatMiles, tituloTarjeta } from '../utils/formato'

export interface TarjetaDiaProps {
  prediccion: Prediccion
  /**
   * Posición de esta predicción dentro de `predicciones[]` (0 = hoy,
   * 1 = mañana, 2 = pasado mañana). El backend ya entrega el arreglo
   * ordenado por fecha ascendente con "hoy" en `America/Lima` primero
   * (HU-02); este componente no reordena ni recalcula fechas, solo usa el
   * índice para decidir el título.
   */
  index: number
}

/**
 * Tarjeta de un día de predicción (HU-01, HU-02, HU-03;
 * specs/06-frontend.md §2, specs/01-producto.md §5).
 */
export function TarjetaDia({ prediccion, index }: TarjetaDiaProps) {
  const { fecha, visitantes_estimados, rango, nivel_afluencia, clima_disponible, clima, factores } =
    prediccion

  const titulo = tituloTarjeta(fecha, index)

  return (
    <article className="tarjeta-dia" aria-label={titulo}>
      <h3>{titulo}</h3>
      <p className="tarjeta-dia__fecha">{formatFechaCorta(fecha)}</p>

      {clima_disponible && clima ? (
        <p className="tarjeta-dia__clima">
          {clima.icono_url ? <img src={clima.icono_url} alt={clima.condicion} width={32} height={32} /> : null}
          {clima.condicion}
        </p>
      ) : (
        <p className="tarjeta-dia__clima tarjeta-dia__clima--sin-datos">
          <span aria-hidden="true">🚫</span> Estimación solo con calendario
        </p>
      )}

      <p className="tarjeta-dia__numero">{formatMiles(visitantes_estimados)}</p>
      <p className="tarjeta-dia__rango">
        entre {formatMiles(rango.min)} y {formatMiles(rango.max)} personas
      </p>

      <ChipNivel nivel_afluencia={nivel_afluencia} />

      <DesgloseFactores factores={factores} />
    </article>
  )
}
