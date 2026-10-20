import { ResponseError } from '@ilpachi/use-alova'
import { httpErrorMessage } from '../../shared/helpers/http-errors'

/** Dettaglio di errore del backend (`detail[]`). */
interface IErrorDetail {
  msg?: string
  code?: string
  params?: Record<string, string | number>
}

/**
 * Testo leggibile di un errore di richiesta: per ogni voce di `detail` usa la traduzione
 * `errors.codes.<code>` (se esiste) e altrimenti `msg`.
 *
 * @param error - errore catturato (di norma `ResponseError`)
 * @param t - funzione di traduzione di vue-i18n
 * @param te - verifica di esistenza di una chiave di vue-i18n
 * @returns messaggio (voci separate da "; ")
 */
export async function describeError(
  error: unknown,
  t: (key: string, params?: Record<string, unknown>) => string,
  te: (key: string) => boolean,
): Promise<string> {
  if (error instanceof ResponseError) {
    const body: unknown = await error.safeResponseData()
    const detail = body !== null && typeof body === 'object' ? (body as { detail?: unknown }).detail : undefined
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail.length > 0) {
      return (detail as IErrorDetail[])
        .map((item) => {
          const key = item.code ? `errors.codes.${item.code}` : ''
          return key && te(key) ? t(key, { ...item.params }) : (item.msg ?? '')
        })
        .filter(Boolean)
        .join('; ')
    }
  }
  return httpErrorMessage(error)
}
