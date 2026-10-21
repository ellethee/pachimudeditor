import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type {
  ILiveEcho,
  ILiveInfo,
  ILiveLoad,
  ILivePlayerSet,
  ILivePlayerSetResult,
  ILivePlayerState,
  ILiveStatus,
  ILiveWho,
  ILiveZone,
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
 * Crea mob o oggetti.
 *
 * @param kind - `mob` o `obj`
 * @param load - vnum, destinazione e quantità
 */
export async function loadLive(kind: 'mob' | 'obj', load: ILiveLoad): Promise<{ loaded: Record<string, unknown>[] }> {
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
