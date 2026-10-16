import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type {
  IEnumOptions,
  IExtraDescription,
  IExtraDescriptionInput,
  IPaginatedRooms,
  IResetUsage,
  IRoom,
  IRoomDetail,
  IRoomExit,
  IRoomExitInput,
  IRoomGraph,
  IRoomInput,
  IZoneRef,
} from '../types/rooms'

/** Opzioni per-richiesta (alova): `autoError: false` silenzia il dialog globale degli errori. */
export interface IRequestOptions {
  autoError?: boolean
}

/**
 * Client HTTP dell'app (@ilpachi/use-alova, cablato da createPachiApp): Authorization, refresh del
 * token, spinner e messaggi di errore sono già gestiti. Risolto a ogni chiamata.
 */
function http() {
  return getUseAlovaInstance()({ url: '/api' }).alova
}

/** Enum del backend (terreni, direzioni, porte). */
export async function getEnums(): Promise<IEnumOptions> {
  return http().Get<IEnumOptions>('/meta/enums', { cacheFor: 0 })
}

/** Tutte le zone (senza `page`/`pageSize` il backend non pagina). */
export async function listZones(): Promise<IZoneRef[]> {
  const page = await http().Get<IPaginatedRooms<IZoneRef>>('/zones', { cacheFor: 0 })
  return page.items
}

/** Primo vnum libero per una nuova stanza nella zona. */
export async function nextRoomVnum(zoneId: number): Promise<number> {
  return http().Get<number>(`/zones/${zoneId}/next-vnum`, { params: { kind: 'room' }, cacheFor: 0 })
}

/** Tutte le stanze (di tutte le zone: le uscite possono attraversare le zone). */
export async function listAllRooms(): Promise<IRoom[]> {
  const page = await http().Get<IPaginatedRooms>('/rooms', { cacheFor: 0 })
  return page.items
}

/** Grafo (nodi e archi) delle stanze di una zona. */
export async function getRoomGraph(zoneId: number): Promise<IRoomGraph> {
  return http().Get<IRoomGraph>('/rooms/graph', { params: { zoneId }, cacheFor: 0 })
}

/** Dettaglio di una stanza con uscite ed extra description. */
export async function getRoom(id: number): Promise<IRoomDetail> {
  return http().Get<IRoomDetail>(`/rooms/${id}`, { cacheFor: 0 })
}

/** Crea una stanza. */
export async function createRoom(payload: IRoomInput, options: IRequestOptions = {}): Promise<IRoomDetail> {
  return http().Post<IRoomDetail>('/rooms', payload, { cacheFor: 0, ...options })
}

/** Aggiorna una stanza (patch parziale). */
export async function updateRoom(
  id: number,
  payload: Partial<IRoomInput>,
  options: IRequestOptions = {},
): Promise<IRoomDetail> {
  return http().Put<IRoomDetail>(`/rooms/${id}`, payload, { cacheFor: 0, ...options })
}

/** Elenca i comandi di reset che referenziano la stanza. */
export async function getRoomUsage(id: number): Promise<IResetUsage[]> {
  return http().Get<IResetUsage[]>(`/rooms/${id}/usage`, { cacheFor: 0 })
}

/** Clona una stanza (extra description copiate, uscite no). */
export async function cloneRoom(
  id: number,
  payload: { vnum: number; name?: string | undefined },
  options: IRequestOptions = {},
): Promise<IRoomDetail> {
  return http().Post<IRoomDetail>(`/rooms/${id}/clone`, payload, { cacheFor: 0, ...options })
}

/** Crea un'uscita. */
export async function createExit(
  roomId: number,
  payload: IRoomExitInput,
  options: IRequestOptions = {},
): Promise<IRoomExit> {
  return http().Post<IRoomExit>(`/rooms/${roomId}/exits`, payload, { cacheFor: 0, ...options })
}

/** Aggiorna un'uscita. */
export async function updateExit(
  roomId: number,
  exitId: number,
  payload: Partial<IRoomExitInput>,
  options: IRequestOptions = {},
): Promise<IRoomExit> {
  return http().Put<IRoomExit>(`/rooms/${roomId}/exits/${exitId}`, payload, { cacheFor: 0, ...options })
}

/** Elimina un'uscita. */
export async function removeExit(roomId: number, exitId: number, options: IRequestOptions = {}): Promise<void> {
  await http().Delete(`/rooms/${roomId}/exits/${exitId}`, { cacheFor: 0, ...options })
}

/** Crea una extra description. */
export async function createExtra(
  roomId: number,
  payload: IExtraDescriptionInput,
  options: IRequestOptions = {},
): Promise<IExtraDescription> {
  return http().Post<IExtraDescription>(`/rooms/${roomId}/extra-descriptions`, payload, { cacheFor: 0, ...options })
}

/** Aggiorna una extra description. */
export async function updateExtra(
  roomId: number,
  extraId: number,
  payload: Partial<IExtraDescriptionInput>,
  options: IRequestOptions = {},
): Promise<IExtraDescription> {
  return http().Put<IExtraDescription>(`/rooms/${roomId}/extra-descriptions/${extraId}`, payload, {
    cacheFor: 0,
    ...options,
  })
}

/** Elimina una extra description. */
export async function removeExtra(roomId: number, extraId: number, options: IRequestOptions = {}): Promise<void> {
  await http().Delete(`/rooms/${roomId}/extra-descriptions/${extraId}`, { cacheFor: 0, ...options })
}
