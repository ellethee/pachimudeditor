import { getPachiI18n, pachiT } from '@ilpachi/pachi-i18n'

/** Opzione di enum come restituita da `GET /api/meta/enums` (`value` numerico o stringa). */
export interface IEnumLabelOption {
  value: number | string
  label: string
}

/**
 * Etichetta localizzata di un valore di enum: `enumLabels.<name>.<value>` se la traduzione esiste
 * (it/en), altrimenti l'etichetta (inglese) restituita dal backend.
 *
 * @param name - nome dell'enum come chiave di `/api/meta/enums` (es. `sectorType`)
 * @param option - opzione `{ value, label }` del backend
 * @returns testo da mostrare
 */
export function enumLabel(name: string, option: IEnumLabelOption): string {
  const key = `enumLabels.${name}.${option.value}`
  const global = getPachiI18n()?.global as unknown as { te: (key: string) => boolean } | undefined
  return global?.te(key) ? pachiT(key) : option.label
}

/**
 * Localizza le etichette di un elenco di opzioni (mantiene `value`).
 *
 * @param name - nome dell'enum
 * @param options - opzioni del backend
 */
export function localizeOptions<T extends IEnumLabelOption>(name: string, options: T[]): T[] {
  return options.map((option) => ({ ...option, label: enumLabel(name, option) }))
}

/**
 * Localizza tutte le liste di opzioni di un oggetto enum (`{ sectorType: [...], ... }`). Le chiavi
 * non-array vengono lasciate invariate.
 *
 * @param enums - risposta di `GET /api/meta/enums`
 * @returns una copia con le etichette tradotte
 */
export function localizeEnums<T extends object>(enums: T): T {
  const out: Record<string, unknown> = {}
  for (const [name, value] of Object.entries(enums)) {
    out[name] = Array.isArray(value) ? localizeOptions(name, value as IEnumLabelOption[]) : value
  }
  return out as T
}
