import { AuthManager } from '@ilpachi/pachifastquasar'
import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type { IImportPreview, IZoneRef } from '../types/transfer'

/** Errore HTTP di una richiesta `fetch` del modulo: conserva il corpo JSON (`{ detail: [...] }`). */
export class TransferHttpError extends Error {
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
 * Esegue una `fetch` autenticata e solleva `TransferHttpError` se la risposta non è 2xx.
 * (Si usa `fetch` e non il client alova perché servono il download binario e l'upload multipart.)
 * @param url URL relativo
 * @param init opzioni della richiesta
 */
async function authedFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(url, { ...init, headers: { ...authHeaders(), ...(init.headers ?? {}) } })
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      body = null
    }
    throw new TransferHttpError(response.status, body)
  }
  return response
}

/** Elenco completo delle zone (senza paginazione). */
export async function listZones(): Promise<IZoneRef[]> {
  const { alova } = getUseAlovaInstance()({ url: '/api/zones' })
  const page = await alova.Get<{ items: IZoneRef[] } | IZoneRef[]>('', { cacheFor: 0 })
  return Array.isArray(page) ? page : page.items
}

/**
 * Scarica lo zip della zona (`GET /api/transfer/zones/{id}/export`) e lo salva con il nome indicato dal server.
 * @param zoneId id della zona
 * @returns il nome del file salvato
 */
export async function downloadZoneExport(zoneId: number): Promise<string> {
  const response = await authedFetch(`/api/transfer/zones/${zoneId}/export`)
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^";]+)"?/.exec(disposition)
  const fileName = match?.[1] ?? `zone-${zoneId}.zip`
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
  return fileName
}

/**
 * Importa una zona dai file caricati.
 * @param files uno zip e/o i file `zone/rooms/mobs/objects/resets .yaml`
 * @param apply `false` = anteprima (dry-run); `true` = import vero (invia `dryRun=false&confirm=true`)
 * @returns anteprima/riepilogo
 */
export async function importZone(files: File[], apply: boolean): Promise<IImportPreview> {
  const form = new FormData()
  for (const file of files) form.append('files', file, file.name)
  const query = apply ? 'dryRun=false&confirm=true' : 'dryRun=true'
  const response = await authedFetch(`/api/transfer/zones/import?${query}`, { method: 'POST', body: form })
  const body = (await response.json()) as { data: IImportPreview }
  return body.data
}
