import type { Prediccion } from '../api/client'

export interface DesgloseFactoresProps {
  factores: Prediccion['factores']
}

/** `"× 1.20"`, `"× 0.70"`, etc. (HU-03: "cada factor muestra su valor, ej. × 0.65"). */
function formatValorFactor(valor: number): string {
  return `× ${valor.toFixed(2)}`
}

/**
 * Desglose de factores de una predicción (HU-03, specs/06-frontend.md §2).
 *
 * Implementado con `<details>`/`<summary>` nativos de HTML: cerrado por
 * defecto y accesible por teclado sin JS adicional. No recalcula nada en el
 * cliente (front.md, "honestidad de datos"): el backend ya garantiza que el
 * producto redondeado de base × factores coincide con `visitantes_estimados`
 * (salvo el tope de capacidad), este componente solo **muestra**
 * `base_diaria` y cada factor tal cual vienen en la respuesta.
 */
export function DesgloseFactores({ factores }: DesgloseFactoresProps) {
  return (
    <details className="desglose-factores">
      <summary>¿Por qué este número?</summary>
      <ul>
        <li>Base diaria: {factores.base_diaria}</li>
        <li>
          Temporada: {formatValorFactor(factores.temporada.valor)} — {factores.temporada.razon}
        </li>
        <li>
          Día de la semana: {formatValorFactor(factores.dia_semana.valor)} —{' '}
          {factores.dia_semana.razon}
        </li>
        <li>
          Feriado: {formatValorFactor(factores.feriado.valor)} — {factores.feriado.razon}
        </li>
        <li>
          Clima: {formatValorFactor(factores.clima.valor)} — {factores.clima.razon}
        </li>
      </ul>
      {factores.tope_capacidad_aplicado && (
        <p>Se aplicó el tope de capacidad diaria de la cueva.</p>
      )}
    </details>
  )
}
