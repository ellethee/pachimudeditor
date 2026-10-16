import { getUseAlovaInstance } from '@ilpachi/use-alova'
import { parseValidation } from '../utils/reset-issues'
import type {
  IResetCommand,
  IResetIssue,
  IResetCommandInput,
  IZone,
  IZoneCloneInput,
  IZoneInput,
  IZoneVnumSuggestion,
} from '../types/zones'

/**
 * Client HTTP dell'app (@ilpachi/use-alova, cablato da createPachiApp): Authorization, refresh del
 * token, spinner e messaggi di errore sono già gestiti. Risolto a ogni chiamata, così non dipende
 * dall'ordine di inizializzazione dei boot.
 */
function http() {
  return getUseAlovaInstance()({ url: '/api/zones' }).alova
}

/**
 * Elenco completo delle zone (senza paginazione: il backend restituisce tutte le righe se mancano `page` e `pageSize`).
 * @returns le zone ordinate per vnum
 */
export async function listAllZones(): Promise<IZone[]> {
  const page = await http().Get<{ items: IZone[] }>('')
  return page.items
}

/**
 * Una zona per id (deep-link `?zoneId=`); l'errore non apre il dialogo globale: lo gestisce il chiamante.
 * @param id id della zona
 */
export async function getZone(id: number): Promise<IZone> {
  return http().Get<IZone>(`/${id}`, { cacheFor: 0, meta: { autoError: false } })
}

/**
 * Crea una zona con `POST /api/zones` (il backend accetta anche lo slash finale usato da `createRecord`
 * di pachi-table2).
 * Gli errori non mostrano il dialogo globale: li gestisce il chiamante.
 * @param data dati della zona
 */
export async function createZone(data: IZoneInput): Promise<IZone> {
  return http().Post<IZone>('', data, { meta: { autoError: false } })
}

/**
 * Suggerisce il prossimo vnum libero con il relativo range di vnum.
 * @param span ampiezza del range (default del backend)
 * @param silent se true non mostra il dialogo d'errore globale
 */
export async function getNextZoneVnum(span?: number, silent = false): Promise<IZoneVnumSuggestion> {
  return http().Get<IZoneVnumSuggestion>('/next-vnum', {
    params: span === undefined ? {} : { span },
    meta: silent ? { autoError: false, spinner: false } : {},
  })
}

/**
 * Clona una zona (configurazione, non il contenuto).
 * @param zoneId id della zona sorgente
 * @param data nuovo vnum/nome e flag di copia dello script di reset
 * Gli errori non mostrano il dialogo globale: li gestisce il chiamante.
 */
export async function cloneZone(zoneId: number, data: IZoneCloneInput): Promise<IZone> {
  return http().Post<IZone>(`/${zoneId}/clone`, data, { meta: { autoError: false } })
}

/**
 * Legge lo script di reset di una zona, già in ordine di esecuzione.
 * @param zoneId id della zona
 */
export async function getResetCommands(zoneId: number): Promise<IResetCommand[]> {
  return http().Get<IResetCommand[]>(`/${zoneId}/reset-commands`)
}

/**
 * Sostituisce l'intero script di reset di una zona (l'ordine è la posizione nella lista).
 * @param zoneId id della zona
 * @param commands i nuovi passi
 */
export async function replaceResetCommands(
  zoneId: number,
  commands: IResetCommandInput[],
): Promise<IResetCommand[]> {
  // errori gestiti dal chiamante (elenco per passo), senza il dialogo globale
  return http().Put<IResetCommand[]>(`/${zoneId}/reset-commands`, { commands }, { meta: { autoError: false } })
}

/**
 * Valida lo script di reset (`POST /api/zones/{id}/reset-commands/validate`) senza salvarlo.
 * La forma della risposta non è definitiva: `parseValidation` accetta un array di
 * `{ index, level: 'error'|'warning', code?, params?, message? }` o un oggetto con `issues`/`errors`/`warnings`.
 * Per cambiare contratto basta modificare questa funzione (e/o `parseValidation`).
 *
 * @param zoneId id della zona
 * @param commands i passi correnti (anche non salvati)
 * @returns i problemi trovati (vuoto = nessun problema)
 */
export async function validateResetCommands(
  zoneId: number,
  commands: IResetCommandInput[],
): Promise<IResetIssue[]> {
  const data = await http().Post<unknown>(
    `/${zoneId}/reset-commands/validate`,
    { commands },
    { meta: { autoError: false } },
  )
  return parseValidation(data)
}
