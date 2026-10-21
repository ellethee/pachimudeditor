import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type {
  IPlayerDetail,
  IPlayerInventory,
  IPlayerItemAdd,
  IPlayerPage,
  IPlayerPatch,
  IPlayersInfo,
  IPlayersStatus,
  IPlayerWriteOptions,
} from '../types/player-files'

/** Client HTTP dell'app (auth, refresh e `X-World` già gestiti), risolto a ogni chiamata. */
function http() {
  return getUseAlovaInstance()({ url: '/api/world/players' }).alova
}

/** Opzioni comuni: nessuna cache, gli errori li mostra la UI. */
const OPTS = { cacheFor: 0, meta: { autoError: false } } as const

/** Descrittore dei giocatori del mondo attivo (colonne, campi, tabelle). */
export async function getPlayersInfo(): Promise<IPlayersInfo> {
  return http().Get<IPlayersInfo>('/info', OPTS)
}

/** Stato del server di gioco, se rilevabile (mai bloccante: un errore vale «sconosciuto»). */
export async function getPlayersStatus(): Promise<IPlayersStatus> {
  return http().Get<IPlayersStatus>('/status', { ...OPTS, meta: { autoError: false, spinner: false } })
}

/**
 * Pagina dell'elenco.
 *
 * @param params - `page`, `pageSize`, `search`, `orderBy` (con `-` per il discendente)
 */
export async function listPlayers(params: Record<string, string | number>): Promise<IPlayerPage> {
  return http().Get<IPlayerPage>('', { ...OPTS, params })
}

/**
 * Dettaglio di un giocatore.
 *
 * @param id - id opaco
 */
export async function getPlayer(id: string): Promise<IPlayerDetail> {
  return http().Get<IPlayerDetail>(`/${encodeURIComponent(id)}`, OPTS)
}

/**
 * Inventario ed equipaggiamento di un giocatore.
 *
 * @param id - id opaco
 */
export async function getPlayerInventory(id: string): Promise<IPlayerInventory> {
  return http().Get<IPlayerInventory>(`/${encodeURIComponent(id)}/inventory`, OPTS)
}

/**
 * Modifica i campi di un giocatore (solo quelli presenti nel patch).
 *
 * @param id - id opaco
 * @param patch - `details`/`lists` da cambiare, `revision` letta e conferma del server acceso
 */
export async function updatePlayer(id: string, patch: IPlayerPatch): Promise<IPlayerDetail> {
  return http().Patch<IPlayerDetail>(`/${encodeURIComponent(id)}`, patch, OPTS)
}

/**
 * Aggiunge un oggetto (per vnum) all'inventario o all'equipaggiamento.
 *
 * @param id - id opaco del giocatore
 * @param item - vnum, slot o contenitore, `revision` e conferma
 */
export async function addPlayerItem(id: string, item: IPlayerItemAdd): Promise<IPlayerInventory> {
  return http().Post<IPlayerInventory>(`/${encodeURIComponent(id)}/inventory/items`, item, OPTS)
}

/**
 * Cambia lo slot di un oggetto di primo livello.
 *
 * @param id - id opaco del giocatore
 * @param itemId - posizione dell'oggetto (`IPlayerItem.id`)
 * @param wearSlot - nuovo slot, `null` = portato
 * @param options - `revision` e conferma
 */
export async function updatePlayerItem(
  id: string,
  itemId: number,
  wearSlot: string | null,
  options: IPlayerWriteOptions,
): Promise<IPlayerInventory> {
  return http().Patch<IPlayerInventory>(`/${encodeURIComponent(id)}/inventory/items/${itemId}`, { ...options, wearSlot }, OPTS)
}

/**
 * Toglie un oggetto con il suo contenuto.
 *
 * @param id - id opaco del giocatore
 * @param itemId - posizione dell'oggetto
 * @param options - `revision` e conferma (vanno in query)
 */
export async function removePlayerItem(id: string, itemId: number, options: IPlayerWriteOptions): Promise<IPlayerInventory> {
  const params: Record<string, string> = {}
  if (options.revision) params.revision = options.revision
  if (options.confirmServerRunning) params.confirmServerRunning = 'true'
  return http().Delete<IPlayerInventory>(`/${encodeURIComponent(id)}/inventory/items/${itemId}`, undefined, { ...OPTS, params })
}

/** Opzioni degli enum del mondo (`GET /api/meta/enums`: chiave -> `[{value, label}]`). */
export async function getPlayerEnums(): Promise<Record<string, unknown>> {
  return getUseAlovaInstance()({ url: '/api/meta' }).alova.Get<Record<string, unknown>>('/enums', OPTS)
}
