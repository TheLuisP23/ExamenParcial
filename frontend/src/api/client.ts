/**
 * Cliente HTTP tipado para la API del predictor.
 *
 * Los tipos vienen de `src/api/schema.ts`, generado desde el contrato
 * `specs/openapi.yaml` con `openapi-typescript` (`npm run gen:api`).
 * No se declaran a mano interfaces que dupliquen ese contrato
 * (specs/06-frontend.md §5, specs/00-constitucion.md P1).
 *
 * La URL base es relativa (`/api/v1`): en producción Nginx (infra/nginx/default.conf)
 * hace de proxy inverso hacia el contenedor `api`; en desarrollo (`npm run dev`)
 * el proxy de Vite (`vite.config.ts` → `server.proxy['/api']`) apunta a
 * `http://localhost:8000`. El host nunca se hardcodea (specs/06-frontend.md §4).
 */
import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

export const API_BASE_URL = '/api/v1'

export const apiClient = createClient<paths>({ baseUrl: API_BASE_URL })

export type Health = components['schemas']['Health']
export type PrediccionesResponse = components['schemas']['PrediccionesResponse']
export type Prediccion = components['schemas']['Prediccion']
export type ClimaActual = components['schemas']['ClimaActual']
export type HistoricoMensual = components['schemas']['HistoricoMensual']
export type Modelo = components['schemas']['Modelo']
export type ApiError = components['schemas']['Error']

/** Error tipado con el código y mensaje que devuelve la API (specs/04-api.md §3). */
export class PredictorApiError extends Error {
  constructor(
    public readonly codigo: ApiError['error']['codigo'],
    message: string,
  ) {
    super(message)
    this.name = 'PredictorApiError'
  }
}

function unwrap<T>(result: { data?: T; error?: ApiError }): T {
  if (result.error) {
    throw new PredictorApiError(result.error.error.codigo, result.error.error.mensaje)
  }
  if (result.data === undefined) {
    throw new Error('Respuesta vacía de la API')
  }
  return result.data
}

/** GET /api/v1/health (RF-09) */
export async function getHealth(): Promise<Health> {
  const result = await apiClient.GET('/health')
  return unwrap(result)
}

/**
 * GET /api/v1/predicciones[?fecha=YYYY-MM-DD]
 * Sin `fecha`, devuelve hoy, mañana y pasado mañana (RF-01..05, RF-11).
 */
export async function getPredicciones(fecha?: string): Promise<PrediccionesResponse> {
  const result = await apiClient.GET('/predicciones', {
    params: { query: fecha ? { fecha } : undefined },
  })
  return unwrap(result)
}

/** GET /api/v1/clima/actual (RF-01) */
export async function getClimaActual(): Promise<ClimaActual> {
  const result = await apiClient.GET('/clima/actual')
  return unwrap(result)
}

/** GET /api/v1/historico/mensual?meses=1..36 (RF-08) */
export async function getHistoricoMensual(meses = 36): Promise<HistoricoMensual> {
  const result = await apiClient.GET('/historico/mensual', {
    params: { query: { meses } },
  })
  return unwrap(result)
}

/** GET /api/v1/modelo */
export async function getModelo(): Promise<Modelo> {
  const result = await apiClient.GET('/modelo')
  return unwrap(result)
}
