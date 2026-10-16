import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type { IContentRef, IMobEnums, IMobs, IPaginatedMobs, IResetUsage, IZoneRef } from '../types/mobs'

/**
 * Client HTTP dell'app (@ilpachi/use-alova, cablato da createPachiApp): Authorization, refresh del
 * token, spinner e messaggi di errore sono già gestiti. Risolto a ogni chiamata, così non dipende
 * dall'ordine di inizializzazione dei boot.
 *
 * @param url - base URL delle richieste
 */
function http(url: string) {
  return getUseAlovaInstance()({ url }).alova
}

/** Endpoint della risorsa mob (base della tabella). */
export const MOBS_URL = '/api/mobs'

/** Estrae le righe da una risposta paginata `{ items }` oppure da un array semplice. */
function rowsOf<T>(data: { items: T[] } | T[]): T[] {
  return Array.isArray(data) ? data : data.items
}

/**
 * Elenco dei mob (uso programmatico; la tabella carica da sé i dati).
 *
 * @param params - parametri di query (page, pageSize, search, zoneId, orderBy)
 */
export async function listMobs(
  params: { page?: number; pageSize?: number; search?: string; zoneId?: number } = {},
): Promise<IPaginatedMobs> {
  return http(MOBS_URL).Get<IPaginatedMobs>('', { params, cacheFor: 0 })
}

/**
 * Carica tutte le zone per il selettore (senza `page`/`pageSize` il backend non pagina).
 */
export async function listZones(): Promise<IZoneRef[]> {
  return rowsOf(await http('/api/zones').Get<{ items: IZoneRef[] } | IZoneRef[]>('', { cacheFor: 0 }))
}

/** Opzioni degli enum (`GET /api/meta/enums`). */
export async function getEnums(): Promise<IMobEnums> {
  return http('/api/meta').Get<IMobEnums>('/enums', { cacheFor: 0 })
}

/** Razze disponibili (`GET /api/meta/races`). */
export async function listRaces(): Promise<IContentRef[]> {
  return http('/api/meta').Get<IContentRef[]>('/races', { cacheFor: 0 })
}

/** Classi disponibili (`GET /api/meta/classes`). */
export async function listClasses(): Promise<IContentRef[]> {
  return http('/api/meta').Get<IContentRef[]>('/classes', { cacheFor: 0 })
}

/**
 * Prossimo vnum libero nella zona per i mob.
 *
 * @param zoneId - id della zona
 */
export async function nextMobVnum(zoneId: number): Promise<number> {
  return http('/api/zones').Get<number>(`/${zoneId}/next-vnum`, { params: { kind: 'mob' }, cacheFor: 0 })
}

/**
 * Comandi di reset che referenziano il mob.
 *
 * @param id - id del mob
 */
export async function getMobUsage(id: number): Promise<IResetUsage[]> {
  return http(MOBS_URL).Get<IResetUsage[]>(`/${id}/usage`, { cacheFor: 0 })
}

/**
 * Un mob per id (deep-link `?mobId=`); l'errore non apre il dialogo globale: lo gestisce il chiamante.
 *
 * @param id - id del mob
 */
export async function getMob(id: number): Promise<IMobs> {
  return http(MOBS_URL).Get<IMobs>(`/${id}`, { cacheFor: 0, meta: { autoError: false } })
}
