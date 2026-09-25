/**
 * Esqueleto de carga de una `TarjetaDia` (FE-05, specs/06-frontend.md §3:
 * "Cargando → Esqueletos (skeleton) en las 3 tarjetas").
 *
 * Es puramente decorativo (no hay contenido real todavía), así que va con
 * `aria-hidden="true"` para no generar ruido a lectores de pantalla —mismo
 * criterio que ya usa `GraficoHistorico` para su texto "Cargando
 * histórico…" mientras `/historico/mensual` está en vuelo—. La animación de
 * pulso vive en `index.css` (`.esqueleto-linea`) y respeta
 * `prefers-reduced-motion`.
 */
export function EsqueletoTarjetaDia() {
  return (
    <article className="tarjeta-dia tarjeta-dia--esqueleto" aria-hidden="true">
      <div className="esqueleto-linea esqueleto-linea--titulo" />
      <div className="esqueleto-linea esqueleto-linea--corta" />
      <div className="esqueleto-linea esqueleto-linea--corta" />
      <div className="esqueleto-linea esqueleto-linea--numero" />
      <div className="esqueleto-linea esqueleto-linea--media" />
      <div className="esqueleto-linea esqueleto-linea--chip" />
    </article>
  )
}
