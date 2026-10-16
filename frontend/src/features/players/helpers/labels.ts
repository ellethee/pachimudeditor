import { getPachiI18n, pachiT } from '@ilpachi/pachi-i18n'
import type { IOption, IPlayerLookups } from '../types/players'

/**
 * Localizza le etichette di un elenco di opzioni usando `players.<group>.<value>` se esiste.
 *
 * @param group - gruppo di chiavi i18n (`sexes`, `positions`)
 * @param options - opzioni del backend
 */
function localize(group: string, options: IOption[]): IOption[] {
  const global = getPachiI18n()?.global as unknown as { te: (key: string) => boolean } | undefined
  return options.map((option) => {
    const key = `players.${group}.${option.value}`
    return global?.te(key) ? { ...option, label: pachiT(key) } : option
  })
}

/**
 * Copia dei lookup con sesso e posizione tradotti.
 *
 * @param lookups - risposta di `GET /api/players/lookups`
 */
export function localizeLookups(lookups: IPlayerLookups): IPlayerLookups {
  return { ...lookups, sex: localize('sexes', lookups.sex), position: localize('positions', lookups.position) }
}
