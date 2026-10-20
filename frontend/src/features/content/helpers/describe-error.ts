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
 * Ricava un messaggio leggibile da un errore di richiesta: usa `errors.codes.<code>` (con `params`) se la
 * traduzione esiste, altrimenti il `msg` del backend.
 * @param error errore catturato (tipicamente `ResponseError`)
 * @returns testo da mostrare all'utente
 */
export async function describeError(error: unknown): Promise<string> {
  if (error instanceof ResponseError) {
    const body: unknown = await error.safeResponseJson()
    const detail = body !== null && typeof body === 'object' ? (body as { detail?: unknown }).detail : undefined
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const global = getPachiI18n()?.global as unknown as { te: (key: string) => boolean } | undefined
      return (detail as IErrorDetail[])
        .map((item) => {
          const key = item.code ? `errors.codes.${item.code}` : ''
          return key && global?.te(key) ? pachiT(key, { ...item.params }) : (item.msg ?? '')
        })
        .filter(Boolean)
        .join('; ')
    }
  }
  return httpErrorMessage(error)
}
