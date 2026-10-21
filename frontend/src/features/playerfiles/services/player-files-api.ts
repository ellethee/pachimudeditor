import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type { IPlayerDetail, IPlayerInventory, IPlayerPage, IPlayersInfo, IPlayersStatus } from '../types/player-files'

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
