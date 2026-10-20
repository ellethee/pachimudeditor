import { getPachiI18n, pachiT } from '@ilpachi/pachi-i18n'
import { ResponseError } from '@ilpachi/use-alova'
import { httpErrorMessage } from '../../shared/helpers/http-errors'


/** Dettaglio d'errore del backend (`{ detail: [{ loc, msg, code?, params? }] }`). */
interface IErrorDetail {
  msg?: string
  code?: string
  params?: Record<string, string | number>
}

/**
 * Traduce un dettaglio d'errore: `errors.codes.<code>` se esiste la traduzione, altrimenti `msg`.
 * @param item dettaglio d'errore del backend
 */
function translateDetail(item: IErrorDetail): string {
  const key = item.code ? `errors.codes.${item.code}` : ''
  const global = getPachiI18n()?.global as unknown as { te: (key: string) => boolean } | undefined
  if (key && global?.te(key)) return pachiT(key, { ...item.params })
  return item.msg ?? ''
}

/**
 * Ricava un messaggio leggibile da un errore di una richiesta (per `onError` del dialogo di modifica).
 * Le richieste vanno fatte con `meta: { autoError: false }` per non mostrare anche il dialogo globale.
 * @param error errore catturato
 * @returns testo dell'errore tradotto, o il messaggio dell'eccezione
 */
export async function describeError(error: unknown): Promise<string> {
  if (error instanceof ResponseError) {
    const body: unknown = await error.safeResponseData()
    const detail = body !== null && typeof body === 'object' ? (body as { detail?: unknown }).detail : body
    if (Array.isArray(detail) && detail.length > 0) {
      return (detail as IErrorDetail[]).map(translateDetail).filter(Boolean).join(' - ')
    }
    if (typeof detail === 'string' && detail.trim()) return detail
    return httpErrorMessage(error)
  }
  return error instanceof Error ? error.message : String(error)
}
