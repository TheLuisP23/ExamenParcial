import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App'
import * as apiClient from '../src/api/client'
import type { Prediccion, PrediccionesResponse } from '../src/api/client'

// Smoke test del esqueleto (FE-01). Los tests de comportamiento real
// (HU-01..04) llegan con FE-02..FE-05 y QA-04.
//
// `Encabezado`, `PiePagina` (FE-03) y `GraficoHistorico` (FE-04) llaman a
// `/clima/actual`, `/health` y `/historico/mensual` por su cuenta al
// montarse; se mockean aquí para que este smoke test no dependa de la red
// (esos componentes ya tienen su propia cobertura en tests/Encabezado.test.tsx,
// tests/PiePagina.test.tsx y tests/GraficoHistorico.test.tsx).
function prediccionBase(overrides: Partial<Prediccion>): Prediccion {
  return {
    fecha: '2026-09-25',
    visitantes_estimados: 426,
    rango: { min: 341, max: 511 },
    nivel_afluencia: 'Alta',
    clima_disponible: true,
    clima: {
      condicion: 'Lluvia moderada',
      codigo_condicion: 1189,
      icono_url: 'https://cdn.weatherapi.com/weather/64x64/day/302.png',
      temp_max_c: 29.0,
      temp_min_c: 21.4,
      precipitacion_mm: 12.0,
      probabilidad_lluvia: 60,
    },
    factores: {
      base_diaria: 350,
      temporada: { valor: 1.2, razon: 'Setiembre: temporada media' },
      dia_semana: { valor: 1.45, razon: 'Viernes' },
      feriado: { valor: 1.0, razon: 'Día normal' },
      clima: { valor: 0.7, razon: 'Lluvia 12.0 mm (10–25 mm)' },
      tope_capacidad_aplicado: false,
    },
    advertencias: [],
    ...overrides,
  }
}

const PREDICCIONES_EJEMPLO: Prediccion[] = [
  prediccionBase({ fecha: '2026-09-25' }),
  prediccionBase({
    fecha: '2026-09-26',
    visitantes_estimados: 609,
    rango: { min: 487, max: 731 },
    nivel_afluencia: 'Muy alta',
  }),
  prediccionBase({
    fecha: '2026-09-27',
    visitantes_estimados: 142,
    rango: { min: 114, max: 170 },
    nivel_afluencia: 'Baja',
    clima_disponible: false,
    clima: null,
    advertencias: [
      {
        codigo: 'CLIMA_NO_DISPONIBLE',
        mensaje: 'No pudimos obtener el clima. Mostramos una estimación solo con calendario.',
      },
    ],
  }),
]

const RESPUESTA_EJEMPLO: PrediccionesResponse = {
  ubicacion: { nombre: 'PN Tingo María' },
  version_modelo: 'reglas-v1',
  datos_sinteticos: true,
  generado_en: '2026-09-25T08:00:00-05:00',
  predicciones: PREDICCIONES_EJEMPLO,
  atribucion: 'Powered by WeatherAPI.com',
}

/** Mockea los 3 endpoints que no son el foco de un test dado (dejan la promesa pendiente). */
function mockearEndpointsSecundarios() {
  vi.spyOn(apiClient, 'getClimaActual').mockReturnValue(new Promise(() => {}))
  vi.spyOn(apiClient, 'getHealth').mockReturnValue(new Promise(() => {}))
  vi.spyOn(apiClient, 'getHistoricoMensual').mockReturnValue(new Promise(() => {}))
}

describe('App', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renderiza el título de la pantalla principal', () => {
    mockearEndpointsSecundarios()
    vi.spyOn(apiClient, 'getPredicciones').mockReturnValue(new Promise(() => {}))

    render(<App />)

    expect(
      screen.getByRole('heading', {
        name: /cueva de las lechuzas/i,
      }),
    ).toBeInTheDocument()
  })

  it('indica que los datos de visitas son sintéticos (RNF-14)', () => {
    mockearEndpointsSecundarios()
    vi.spyOn(apiClient, 'getPredicciones').mockReturnValue(new Promise(() => {}))

    render(<App />)

    // Con `GraficoHistorico` (FE-04) montado, la advertencia de datos
    // sintéticos aparece dos veces (pie de página y leyenda del histórico);
    // basta con que aparezca al menos una vez.
    expect(screen.getAllByText(/sintéticos/i).length).toBeGreaterThan(0)
  })

  // FE-05 (specs/06-frontend.md §3, RNF-13): "Cargando → Esqueletos
  // (skeleton) en las 3 tarjetas."
  it('estado Cargando: muestra 3 esqueletos mientras /predicciones está en vuelo', () => {
    mockearEndpointsSecundarios()
    vi.spyOn(apiClient, 'getPredicciones').mockReturnValue(new Promise(() => {}))

    const { container } = render(<App />)

    expect(container.querySelectorAll('.tarjeta-dia--esqueleto')).toHaveLength(3)
    // Todavía no hay tarjetas reales ni mensaje de error.
    expect(screen.queryByText(/no pudimos calcular la predicción/i)).not.toBeInTheDocument()
  })

  // Estado de éxito: las 3 TarjetaDia con los datos reales de /predicciones.
  it('estado éxito: reemplaza los esqueletos por las 3 tarjetas con los datos de /predicciones', async () => {
    mockearEndpointsSecundarios()
    vi.spyOn(apiClient, 'getPredicciones').mockResolvedValue(RESPUESTA_EJEMPLO)

    const { container } = render(<App />)

    await waitFor(() => {
      expect(container.querySelectorAll('.tarjeta-dia--esqueleto')).toHaveLength(0)
    })

    expect(screen.getByRole('heading', { name: 'Hoy' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Mañana' })).toBeInTheDocument()
    expect(screen.getByText('426')).toBeInTheDocument()
    expect(screen.getByText('609')).toBeInTheDocument()
    expect(screen.getByText('142')).toBeInTheDocument()
    // clima_disponible=false de la 3ª predicción sigue funcionando con datos reales (ya resuelto por TarjetaDia, FE-02).
    expect(screen.getByText('Estimación solo con calendario')).toBeInTheDocument()
    // La advertencia de esa 3ª predicción se propaga a `Advertencias`.
    expect(screen.getByRole('alert')).toHaveTextContent('No pudimos obtener el clima')
  })

  // FE-05 (specs/06-frontend.md §3; futura FT-04): "500 en /predicciones →
  // mensaje de error y botón Reintentar que vuelve a llamar".
  it('estado error: red caída o 5xx en /predicciones muestra el mensaje y el botón Reintentar', async () => {
    mockearEndpointsSecundarios()
    vi.spyOn(apiClient, 'getPredicciones').mockRejectedValue(new Error('network error'))

    const { container } = render(<App />)

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('No pudimos calcular la predicción. Reintenta en unos minutos.')
    expect(screen.getByRole('button', { name: /reintentar/i })).toBeInTheDocument()
    // Sin tarjetas ni esqueletos una vez que el error ya se resolvió.
    expect(container.querySelectorAll('.tarjeta-dia--esqueleto')).toHaveLength(0)
  })

  it('el botón Reintentar vuelve a llamar a /predicciones y, si responde 200, muestra las tarjetas', async () => {
    mockearEndpointsSecundarios()
    const getPrediccionesMock = vi
      .spyOn(apiClient, 'getPredicciones')
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce(RESPUESTA_EJEMPLO)

    const { container } = render(<App />)

    const boton = await screen.findByRole('button', { name: /reintentar/i })
    expect(getPrediccionesMock).toHaveBeenCalledTimes(1)

    fireEvent.click(boton)

    await waitFor(() => {
      expect(getPrediccionesMock).toHaveBeenCalledTimes(2)
    })
    await waitFor(() => {
      expect(container.querySelectorAll('.tarjeta-dia--esqueleto')).toHaveLength(0)
    })
    expect(screen.getByRole('heading', { name: 'Hoy' })).toBeInTheDocument()
    expect(screen.queryByText(/no pudimos calcular la predicción/i)).not.toBeInTheDocument()
  })
})
