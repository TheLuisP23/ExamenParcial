import '@testing-library/jest-dom/vitest'

/**
 * Gotcha conocido de Recharts + JSDOM/Vitest (afecta a `GraficoHistorico`,
 * FE-04, specs/06-frontend.md §2): `ResponsiveContainer` mide su contenedor
 * con `ResizeObserver` y `Element.getBoundingClientRect()` para calcular el
 * ancho/alto del gráfico. JSDOM no hace layout real: no implementa
 * `ResizeObserver` (queda `undefined`) y `getBoundingClientRect()` siempre
 * devuelve un rect de ceros. Sin este mock, `ResponsiveContainer` nunca ve un
 * tamaño positivo y no renderiza nada dentro (ni el `<svg>` ni las barras),
 * así que cualquier test que busque las barras del gráfico fallaría aunque el
 * componente esté bien. Se define acá, en el setup global, porque es
 * infraestructura de test (no depende de la lógica de un componente en
 * particular) y es inofensivo para el resto de los tests, que no usan
 * `ResizeObserver` ni miden layout.
 */
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const globalAny = globalThis as any
globalAny.ResizeObserver = globalAny.ResizeObserver ?? ResizeObserverMock

Element.prototype.getBoundingClientRect = function getBoundingClientRect() {
  return {
    width: 600,
    height: 280,
    top: 0,
    left: 0,
    bottom: 280,
    right: 600,
    x: 0,
    y: 0,
    toJSON() {
      return {}
    },
  } as DOMRect
}
