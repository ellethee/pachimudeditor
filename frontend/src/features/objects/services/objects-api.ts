import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type { IObjectEnums, IObjects, IPaginatedObjects, IResetUsage, IZoneRef } from '../types/objects'

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

/** Endpoint della risorsa oggetti (base della tabella). */
export const OBJECTS_URL = '/api/objects'

/**
 * Elenco degli oggetti (uso programmatico; la tabella carica da sé i dati).
 *
 * @param params - parametri di query (page, pageSize, search, zoneId, orderBy)
 */
export async function listObjects(
  params: { page?: number; pageSize?: number; search?: string; zoneId?: number } = {},
): Promise<IPaginatedObjects> {
  return http(OBJECTS_URL).Get<IPaginatedObjects>('', { params, cacheFor: 0 })
}

/**
 * Carica tutte le zone per il selettore (senza `page`/`pageSize` il backend non pagina).
 */
export async function listZones(): Promise<IZoneRef[]> {
  const data = await http('/api/zones').Get<{ items: IZoneRef[] } | IZoneRef[]>('', { cacheFor: 0 })
  return Array.isArray(data) ? data : data.items
}

/** Opzioni degli enum (`GET /api/meta/enums`). */
export async function getEnums(): Promise<IObjectEnums> {
  return http('/api/meta').Get<IObjectEnums>('/enums', { cacheFor: 0 })
}

/**
 * Prossimo vnum libero nella zona per gli oggetti.
 *
 * @param zoneId - id della zona
 */
export async function nextObjectVnum(zoneId: number): Promise<number> {
  return http('/api/zones').Get<number>(`/${zoneId}/next-vnum`, { params: { kind: 'object' }, cacheFor: 0 })
}

/**
 * Comandi di reset che referenziano l'oggetto.
 *
 * @param id - id dell'oggetto
 */
export async function getObjectUsage(id: number): Promise<IResetUsage[]> {
  return http(OBJECTS_URL).Get<IResetUsage[]>(`/${id}/usage`, { cacheFor: 0 })
}

/**
 * Un oggetto per id (deep-link `?objectId=`); l'errore non apre il dialogo globale: lo gestisce il chiamante.
 *
 * @param id - id dell'oggetto
 */
export async function getObject(id: number): Promise<IObjects> {
  return http(OBJECTS_URL).Get<IObjects>(`/${id}`, { cacheFor: 0, meta: { autoError: false } })
}
