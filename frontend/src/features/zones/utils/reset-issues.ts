import { getPachiI18n, pachiT } from '@ilpachi/pachi-i18n'
import { ResponseError } from '@ilpachi/use-alova'
import type { IResetIssue } from '../types/zones'

/** Parametri di un codice d'errore (`{ index, vnum, ... }`). */
type TParams = Record<string, string | number>

/**
 * Traduce un codice d'errore del backend (`errors.codes.<code>`); se manca la traduzione usa `fallback`.
 * Il catalogo si rigenera con `pachifast locale export`: codici nuovi non ancora presenti ricadono sul messaggio.
 *
 * @param code - codice (es. `zones.reset_unknown_mob`)
 * @param params - parametri di interpolazione
 * @param fallback - testo di ripiego (messaggio del backend)
 */
export function translateCode(code: string | undefined, params: TParams | undefined, fallback: string): string {
  const key = code ? `errors.codes.${code}` : ''
  const global = getPachiI18n()?.global as unknown as { te: (key: string) => boolean } | undefined
  if (key && global?.te(key)) return pachiT(key, { ...params })
  return fallback
}

/**
 * Indice (0-based) del passo a cui si riferisce un problema, ricavato dai campi noti.
 * Convenzione assunta: `index`/`orderIndex`/`order_index`/`step_index` sono 0-based, `step` è 1-based.
 *
 * @param raw - voce grezza del backend
 * @param params - parametri della voce
 */
function stepIndex(raw: Record<string, unknown>, params: TParams | undefined): number | null {
  const pick = (source: Record<string, unknown> | undefined, keys: string[]): number | null => {
    for (const key of keys) {
      const value = source?.[key]
      if (typeof value === 'number' && Number.isInteger(value)) return value
      if (typeof value === 'string' && /^\d+$/.test(value)) return Number(value)
    }
    return null
  }
  const zeroBased = ['index', 'orderIndex', 'order_index', 'stepIndex', 'step_index']
  const direct = pick(raw, zeroBased) ?? pick(params, zeroBased)
  if (direct !== null) return direct
  const oneBased = pick(raw, ['step']) ?? pick(params, ['step'])
  if (oneBased !== null) return oneBased - 1
  // `loc` stile FastAPI: ["body", "commands", 2, "arg1"]
  if (Array.isArray(raw.loc)) {
    const found = raw.loc.find((part): part is number => typeof part === 'number')
    if (found !== undefined) return found
  }
  return null
}

/**
 * Normalizza una voce grezza (errore di salvataggio o esito della validazione) in `IResetIssue`.
 *
 * @param raw - voce del backend: `{ index?, level|severity?, code?, params?, message|msg? }`
 * @param defaultLevel - livello se la voce non lo dichiara
 */
export function toIssue(raw: unknown, defaultLevel: 'error' | 'warning' = 'error'): IResetIssue {
  if (typeof raw === 'string') return { index: null, level: defaultLevel, text: raw }
  const item = (raw !== null && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const params =
    item.params !== null && typeof item.params === 'object' ? (item.params as TParams) : undefined
  const code = typeof item.code === 'string' ? item.code : undefined
  const message = [item.message, item.msg, item.detail].find((v): v is string => typeof v === 'string') ?? ''
  const rawLevel = String(item.level ?? item.severity ?? defaultLevel).toLowerCase()
  const level = rawLevel.startsWith('warn') ? 'warning' : rawLevel === 'error' ? 'error' : defaultLevel
  return {
    index: stepIndex(item, params),
    level,
    text: translateCode(code, params, message || code || ''),
    ...(code ? { code } : {}),
    ...(params ? { params } : {}),
  }
}

/**
 * Estrae la lista di problemi dalla risposta della validazione. Accetta un array diretto oppure
 * un oggetto con la lista in `issues`/`errors`/`items`/`detail` (e `warnings` a parte).
 *
 * @param data - corpo della risposta
 */
export function parseValidation(data: unknown): IResetIssue[] {
  if (Array.isArray(data)) return data.map((entry) => toIssue(entry))
  if (data !== null && typeof data === 'object') {
    const body = data as Record<string, unknown>
    const out: IResetIssue[] = []
    for (const key of ['issues', 'errors', 'items', 'detail']) {
      if (Array.isArray(body[key])) out.push(...(body[key] as unknown[]).map((entry) => toIssue(entry)))
    }
    if (Array.isArray(body.warnings)) {
      out.push(...(body.warnings as unknown[]).map((entry) => toIssue(entry, 'warning')))
    }
    return out
  }
  return []
}

/**
 * Problemi contenuti in un errore HTTP di salvataggio (`{ detail: [{ code, params, msg }] }`).
 * Per errori non strutturati restituisce un solo problema con il messaggio dell'eccezione.
 *
 * @param error - errore catturato
 */
export async function issuesFromError(error: unknown): Promise<IResetIssue[]> {
  if (error instanceof ResponseError) {
    const body: unknown = await error.safeResponseData()
    const detail = body !== null && typeof body === 'object' ? (body as { detail?: unknown }).detail : body
    if (Array.isArray(detail) && detail.length > 0) return detail.map((entry) => toIssue(entry))
    if (detail !== null && typeof detail === 'object') return [toIssue(detail)]
    if (typeof detail === 'string' && detail.trim()) return [toIssue(detail)]
    return [toIssue(error.message)]
  }
  return [toIssue(error instanceof Error ? error.message : String(error))]
}
