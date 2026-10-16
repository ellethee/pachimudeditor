import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type {
  ContentsPolicy,
  IMobInstanceCreate,
  IMobInstanceDetail,
  IMobInstancePatch,
  IObjectInstanceCreate,
  IObjectInstanceDetail,
  IObjectInstancePatch,
  IPrototypeRef,
  IRoomRef,
  IZoneRef,
  InstanceKind,
} from '../types/instances'

/**
 * Client HTTP dell'app (@ilpachi/use-alova): Authorization, refresh del token e spinner sono già gestiti.
 * Risolto a ogni chiamata per non dipendere dall'ordine di inizializzazione dei boot.
 *
 * @param url - base URL delle richieste
 */
function http(url: string) {
  return getUseAlovaInstance()({ url }).alova
}

/** Opzioni comuni: nessuna cache e nessun dialog automatico (gli errori li mostra il chiamante). */
const OPTS = { cacheFor: 0, meta: { autoError: false } } as const

/** Base URL delle istanze di mob. */
export const MOB_INSTANCES_URL = '/api/instances/mobs'
/** Base URL delle istanze di oggetto. */
export const OBJECT_INSTANCES_URL = '/api/instances/objects'

/**
 * Base URL delle istanze del tipo dato.
 *
 * @param kind - mob o oggetto
 */
export function instancesUrl(kind: InstanceKind): string {
  return kind === 'mob' ? MOB_INSTANCES_URL : OBJECT_INSTANCES_URL
}

/** Estrae le righe da una risposta paginata `{ items }` oppure da un array semplice. */
function rowsOf<T>(data: { items: T[] } | T[]): T[] {
  return Array.isArray(data) ? data : data.items
}

/** Tutte le zone (senza `page`/`pageSize` il backend non pagina). */
export async function listZones(): Promise<IZoneRef[]> {
  return rowsOf(await http('/api/zones').Get<{ items: IZoneRef[] } | IZoneRef[]>('', { cacheFor: 0 }))
}

/**
 * Ricerca di stanze per nome/vnum (prime 25 corrispondenze).
 *
 * @param search - testo cercato
 */
export async function searchRooms(search: string): Promise<IRoomRef[]> {
  const params = { search, page: 1, pageSize: 25, orderBy: 'vnum' }
  return rowsOf(await http('/api/rooms').Get<{ items: IRoomRef[] }>('', { params, cacheFor: 0 }))
}

/**
 * Una stanza dato l'id.
 *
 * @param id - id della stanza
 */
export async function getRoom(id: number): Promise<IRoomRef> {
  return http('/api/rooms').Get<IRoomRef>(`/${id}`, { cacheFor: 0 })
}

/**
 * Ricerca di prototipi (mob o oggetto) per descrizione/keywords/vnum.
 *
 * @param kind - mob o oggetto
 * @param search - testo cercato
 */
export async function searchPrototypes(kind: InstanceKind, search: string): Promise<IPrototypeRef[]> {
  const params = { search, page: 1, pageSize: 25, orderBy: 'vnum' }
  return rowsOf(await http(prototypesUrl(kind)).Get<{ items: IPrototypeRef[] }>('', { params, cacheFor: 0 }))
}

/**
 * Un prototipo dato l'id.
 *
 * @param kind - mob o oggetto
 * @param id - id del prototipo
 */
export async function getPrototype(kind: InstanceKind, id: number): Promise<IPrototypeRef> {
  return http(prototypesUrl(kind)).Get<IPrototypeRef>(`/${id}`, { cacheFor: 0 })
}

/** URL della risorsa prototipi per il tipo dato. */
function prototypesUrl(kind: InstanceKind): string {
  return kind === 'mob' ? '/api/mobs' : '/api/objects'
}

/** Un mob vivo con gli oggetti che porta. */
export async function getMobInstance(id: number): Promise<IMobInstanceDetail> {
  return http(MOB_INSTANCES_URL).Get<IMobInstanceDetail>(`/${id}`, { cacheFor: 0 })
}

/** Genera un mob vivo da un prototipo. */
export async function createMobInstance(body: IMobInstanceCreate): Promise<IMobInstanceDetail> {
  return http(MOB_INSTANCES_URL).Post<IMobInstanceDetail>('', body, OPTS)
}

/** Modifica un mob vivo (patch parziale). */
export async function updateMobInstance(id: number, body: IMobInstancePatch): Promise<IMobInstanceDetail> {
  return http(MOB_INSTANCES_URL).Put<IMobInstanceDetail>(`/${id}`, body, OPTS)
}

/** Un oggetto vivo con il suo contenuto. */
export async function getObjectInstance(id: number): Promise<IObjectInstanceDetail> {
  return http(OBJECT_INSTANCES_URL).Get<IObjectInstanceDetail>(`/${id}`, { cacheFor: 0 })
}

/** Genera un oggetto vivo da un prototipo. */
export async function createObjectInstance(body: IObjectInstanceCreate): Promise<IObjectInstanceDetail> {
  return http(OBJECT_INSTANCES_URL).Post<IObjectInstanceDetail>('', body, OPTS)
}

/** Modifica un oggetto vivo (patch parziale). */
export async function updateObjectInstance(id: number, body: IObjectInstancePatch): Promise<IObjectInstanceDetail> {
  return http(OBJECT_INSTANCES_URL).Put<IObjectInstanceDetail>(`/${id}`, body, OPTS)
}

/**
 * Elimina (despawn) un'istanza.
 *
 * @param kind - mob o oggetto
 * @param id - id dell'istanza
 * @param contents - destino del contenuto (distruggi o lascia cadere)
 */
export async function deleteInstance(kind: InstanceKind, id: number, contents: ContentsPolicy): Promise<void> {
  await http(instancesUrl(kind)).Delete(`/${id}`, undefined, { params: { contents }, ...OPTS })
}
