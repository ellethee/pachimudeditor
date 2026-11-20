import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type {
  ILiveEcho,
  ILiveInfo,
  ILiveInventory,
  ILiveItem,
  ILiveItemExpect,
  ILiveItemRemoveResult,
  ILiveItemSet,
  ILiveItemSetResult,
  ILiveLoad,
  ILiveLoadResult,
  ILivePlayerSet,
  ILivePlayerSetResult,
  ILivePlayerState,
  ILiveStatus,
  ILiveWho,
  ILiveZone,
  ILiveInstances,
  ILiveZoneReload,
} from '../types/live'

/** Client HTTP dell'app (auth, refresh e `X-World` già gestiti), risolto a ogni chiamata. */
function http() {
  return getUseAlovaInstance()({ url: '/api/world/live' }).alova
}

/** Opzioni comuni: nessuna cache, gli errori li mostra la UI. */
const OPTS = { cacheFor: 0, meta: { autoError: false } } as const
/** Come `OPTS` ma senza spinner globale (sondaggi in secondo piano). */
const QUIET = { cacheFor: 0, meta: { autoError: false, spinner: false } } as const

/** Stato del canale live del mondo attivo (403 se l'utente non è superuser). */
export async function getLiveStatus(): Promise<ILiveStatus> {
  return http().Get<ILiveStatus>('/status', QUIET)
}

/** Giocatori connessi. */
export async function getLiveWho(): Promise<ILiveWho> {
  return http().Get<ILiveWho>('/who', OPTS)
}

/** Stato del server (uptime, giocatori, contatori del mondo). */
export async function getLiveInfo(): Promise<ILiveInfo> {
  return http().Get<ILiveInfo>('/info', OPTS)
}

/** Zone come le vede il gioco. */
export async function getLiveZones(): Promise<ILiveZone[]> {
  return (await http().Get<{ zones: ILiveZone[] }>('/zones', OPTS)).zones
}

/**
 * Valori correnti in memoria di un giocatore connesso.
 *
 * @param name - nome del personaggio
 */
export async function getLivePlayer(name: string): Promise<ILivePlayerState> {
  return http().Get<ILivePlayerState>(`/players/${encodeURIComponent(name)}`, OPTS)
}

/**
 * Modifica un giocatore connesso.
 *
 * @param name - nome del personaggio
 * @param change - campi, salvataggio e conferma per gli immortali
 */
export async function setLivePlayer(name: string, change: ILivePlayerSet): Promise<ILivePlayerSetResult> {
  return http().Patch<ILivePlayerSetResult>(`/players/${encodeURIComponent(name)}`, change, OPTS)
}

/**
 * Forza il reset di una zona.
 *
 * @param zone - indice della zona (da `getLiveZones`)
 * @param onlyIfEmpty - non eseguire se un giocatore è nella zona
 */
export async function resetLiveZone(zone: number, onlyIfEmpty: boolean): Promise<{ zone: number; name: string; executed: boolean }> {
  return http().Post('/zones/reset', { zone, onlyIfEmpty }, OPTS)
}

/**
 * Il gioco rilegge dai file una zona e rifà il reset (estensione pachimud, comando `zone.reload`).
 *
 * @param vnum - vnum della zona
 */
export async function reloadLiveZone(vnum: number): Promise<ILiveZoneReload> {
  return http().Post('/zones/reload', { vnum }, OPTS)
}

/**
 * Toglie un messaggio di bacheca dal gioco acceso, DB e memoria insieme (estensione pachimud, comando `board.delete`).
 *
 * @param boardId - id della bacheca
 * @param messageId - id riga del messaggio (`IBoardMessage.id`), non la posizione
 */
export async function deleteLiveBoardMessage(boardId: string, messageId: number): Promise<{ boardId: string; id: number; remaining: number }> {
  return http().Delete(`/boards/${encodeURIComponent(boardId)}/messages/${messageId}`, undefined, OPTS)
}

/**
 * Svuota una bacheca nel gioco acceso, DB e memoria insieme (estensione pachimud, comando `board.clear`).
 *
 * @param boardId - id della bacheca
 */
export async function clearLiveBoard(boardId: string): Promise<{ boardId: string; removed: number }> {
  return http().Delete(`/boards/${encodeURIComponent(boardId)}`, undefined, OPTS)
}

/**
 * Istanze in memoria di una zona (mob della zona e oggetti a terra nelle sue stanze; estensione pachimud, comando `instances.list`).
 *
 * @param zoneVnum - vnum della zona
 */
export async function getLiveZoneInstances(zoneVnum: number): Promise<ILiveInstances> {
  return http().Get<ILiveInstances>('/instances', { ...OPTS, params: { zoneVnum, limit: 200 } })
}

/**
 * Crea mob o oggetti.
 *
 * @param kind - `mob` o `obj`
 * @param load - vnum, destinazione e quantità
 */
export async function loadLive(kind: 'mob' | 'obj', load: ILiveLoad): Promise<ILiveLoadResult> {
  return http().Post(`/load/${kind}`, load, OPTS)
}

/**
 * Manda un messaggio nel gioco.
 *
 * @param echo - testo e destinazione
 */
export async function echoLive(echo: ILiveEcho): Promise<{ recipients: number }> {
  return http().Post('/echo', echo, OPTS)
}

/**
 * Inventario ed equipaggiamento LIVE di un giocatore connesso (409 `worldlive.command_disabled` se il MUD non ha la feature).
 *
 * @param name - nome del personaggio
 */
export async function getLiveInventory(name: string): Promise<ILiveInventory> {
  return http().Get<ILiveInventory>(`/players/${encodeURIComponent(name)}/inventory`, OPTS)
}

/**
 * Un oggetto del giocatore con i campi di sola lettura (il `ref` va in query: contiene `:` e `/`).
 *
 * @param name - nome del personaggio
 * @param ref - riferimento dell'oggetto, dall'ultima lettura dell'elenco
 */
export async function getLiveItem(name: string, ref: string): Promise<ILiveItem> {
  return http().Get<ILiveItem>(`/players/${encodeURIComponent(name)}/inventory/item`, { ...OPTS, params: { ref } })
}

/**
 * Modifica un oggetto (409 `worldlive.stale_ref` se non coincide con `expect`).
 *
 * @param name - nome del personaggio
 * @param ref - riferimento dell'oggetto
 * @param change - `expect` dell'ultima lettura, campi cambiati e salvataggio
 */
export async function setLiveItem(name: string, ref: string, change: ILiveItemSet): Promise<ILiveItemSetResult> {
  return http().Patch<ILiveItemSetResult>(`/players/${encodeURIComponent(name)}/inventory/item`, change, { ...OPTS, params: { ref } })
}

/**
 * Toglie e distrugge un oggetto (con il suo contenuto).
 *
 * @param name - nome del personaggio
 * @param ref - riferimento dell'oggetto
 * @param expect - vnum e impronta dell'ultima lettura
 */
export async function removeLiveItem(name: string, ref: string, expect: ILiveItemExpect): Promise<ILiveItemRemoveResult> {
  const params: Record<string, string | number> = { ref, fp: expect.fp }
  if (expect.vnum !== null) params.vnum = expect.vnum
  return http().Delete<ILiveItemRemoveResult>(`/players/${encodeURIComponent(name)}/inventory/item`, undefined, { ...OPTS, params })
}
