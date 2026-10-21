import { ResponseError } from '@ilpachi/use-alova'

/**
 * Codice stabile del primo dettaglio di un errore del backend (`worldplayers.conflict`, ...), se c'è.
 *
 * @param error - errore catturato
 * @returns il codice oppure `undefined`
 */
export async function errorCode(error: unknown): Promise<string | undefined> {
  if (!(error instanceof ResponseError)) return undefined
  const body: unknown = await error.safeResponseJson()
  const detail = body !== null && typeof body === 'object' ? (body as { detail?: unknown }).detail : undefined
  const first: unknown = Array.isArray(detail) ? detail[0] : undefined
  return first !== null && typeof first === 'object' ? (first as { code?: string }).code : undefined
}
