import type { Prediccion } from '../api/client'

type NivelAfluencia = Prediccion['nivel_afluencia']

/**
 * Colores por nivel (specs/06-frontend.md §2): Baja = verde, Media = azul,
 * Alta = ámbar, Muy alta = rojo. El color es solo refuerzo visual: la
 * etiqueta de texto siempre está presente, nunca es el único portador del
 * significado (accesibilidad, front.md directriz 5 / HU-01).
 */
const ESTILOS: Record<NivelAfluencia, { fondo: string; texto: string; borde: string }> = {
  Baja: { fondo: '#e6f4ea', texto: '#1e7b34', borde: '#a6d8b5' },
  Media: { fondo: '#e8f0fe', texto: '#1a56db', borde: '#a9c5f5' },
  Alta: { fondo: '#fef3e2', texto: '#92600a', borde: '#f3ca82' },
  'Muy alta': { fondo: '#fdecec', texto: '#b3261e', borde: '#f3a9a4' },
}

export interface ChipNivelProps {
  nivel_afluencia: NivelAfluencia
}

/** Chip de nivel de afluencia (HU-01, specs/06-frontend.md §2). */
export function ChipNivel({ nivel_afluencia }: ChipNivelProps) {
  const estilo = ESTILOS[nivel_afluencia]
  return (
    <span
      className="chip-nivel"
      style={{
        backgroundColor: estilo.fondo,
        color: estilo.texto,
        border: `1px solid ${estilo.borde}`,
        borderRadius: '999px',
        padding: '0.15rem 0.6rem',
        fontSize: '0.85rem',
        fontWeight: 600,
        display: 'inline-block',
      }}
    >
      {nivel_afluencia}
    </span>
  )
}
