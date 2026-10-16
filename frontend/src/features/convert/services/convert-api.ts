import { AuthManager } from '@ilpachi/pachifastquasar'
import type { IConvertRequest, IConvertReport, IPairs, IZoneRef } from '../types/convert'

/** Errore HTTP di una richiesta del modulo: conserva il corpo JSON (`{ detail: [...] }`). */
export class ConvertHttpError extends Error {
  /**
   * @param status codice HTTP
   * @param body corpo della risposta, se JSON
   */
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(`HTTP ${status}`)
  }
}

/** Intestazione `Authorization` dell'utente corrente (vuota se non autenticato). */
function authHeaders(): Record<string, string> {
  const auth = AuthManager.getInstance()
  return auth.accessToken ? { Authorization: `${auth.tokenType ?? 'Bearer'} ${auth.accessToken}` } : {}
}

/**
 * `fetch` autenticata che restituisce il campo `data` dell'envelope; solleva `ConvertHttpError` se non 2xx.
 * @param url URL relativo
 * @param init opzioni (gli header si sommano a quelli di autenticazione)
 */
async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { ...init, headers: { ...authHeaders(), ...(init.headers ?? {}) } })
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      body = null
    }
    throw new ConvertHttpError(response.status, body)
  }
  return ((await response.json()) as { data: T }).data
}

/** Mondi e coppie ammesse. */
export function getPairs(): Promise<IPairs> {
  return request<IPairs>('/api/convert/pairs')
}

/**
 * Zone di un mondo qualsiasi (non quello attivo): `X-World` esplicito, che l'interceptor globale non sovrascrive.
 * @param worldId id del mondo
 */
export async function listZonesOf(worldId: string): Promise<IZoneRef[]> {
  const page = await request<{ items: IZoneRef[] }>('/api/zones?pageSize=1000', { headers: { 'X-World': worldId } })
  return page.items
}

/**
 * Anteprima della conversione (non scrive nulla).
 * @param body piano e mondi
 */
export function preview(body: IConvertRequest): Promise<IConvertReport> {
  return request<IConvertReport>('/api/convert/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...body, dryRun: true, confirm: false }),
  })
}

/**
 * Conversione vera (`dryRun=false`, `confirm=true`).
 * @param body piano e mondi
 */
export function run(body: IConvertRequest): Promise<IConvertReport> {
  return request<IConvertReport>('/api/convert/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...body, dryRun: false, confirm: true }),
  })
}
