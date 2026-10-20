import { getPachiI18n, pachiT } from '@ilpachi/pachi-i18n'
import { ResponseError } from '@ilpachi/use-alova'

/**
 * Messaggio tradotto per un errore senza dettaglio dal backend: lo stato HTTP (`errors.http.status.<n>`),
 * l'assenza di risposta (rete/timeout: `errors.http.network`) oppure, per le eccezioni non HTTP, il loro
 * messaggio. In ogni altro caso `errors.http.generic`.
 *
 * @param error - errore catturato
 * @returns testo da mostrare all'utente
 */
export function httpErrorMessage(error: unknown): string {
  if (error instanceof ResponseError) {
    if (!error.response) return pachiT('errors.http.network')
    const key = `errors.http.status.${error.status}`
    const global = getPachiI18n()?.global as unknown as { te: (key: string) => boolean } | undefined
    return global?.te(key) ? pachiT(key) : pachiT('errors.http.generic')
  }
  return error instanceof Error && error.message ? error.message : pachiT('errors.http.generic')
}

/** Dettaglio di errore del backend (`{ detail: [{ msg, code, params }] }`). */
interface IErrorDetail {
  msg?: string
  code?: string
  params?: Record<string, string | number>
}

/**
 * Testo leggibile e tradotto di un errore di richiesta: `errors.codes.<code>` per ogni voce di `detail`
 * (ripiegando su `msg`), il `detail` testuale, altrimenti `httpErrorMessage`.
 *
 * @param error - errore catturato (di norma `ResponseError`)
 * @returns testo da mostrare all'utente
 */
export async function describeHttpError(error: unknown): Promise<string> {
  if (error instanceof ResponseError) {
    const body: unknown = await error.safeResponseData()
    const detail = body !== null && typeof body === 'object' ? (body as { detail?: unknown }).detail : undefined
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const global = getPachiI18n()?.global as unknown as { te: (key: string) => boolean } | undefined
      const text = (detail as IErrorDetail[])
        .map((item) => {
          const key = item.code ? `errors.codes.${item.code}` : ''
          return key && global?.te(key) ? pachiT(key, { ...item.params }) : (item.msg ?? '')
        })
        .filter(Boolean)
        .join('; ')
      if (text) return text
    }
  }
  return httpErrorMessage(error)
}
