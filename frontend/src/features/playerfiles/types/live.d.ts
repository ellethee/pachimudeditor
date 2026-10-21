/** Tipi di `GET/POST /api/world/live/...` (vedi `docs/backend/contract-live.md`). */

/** Stato del canale: sempre una risposta, mai un errore. */
export type LiveState = 'connected' | 'unreachable' | 'auth_failed' | 'token_missing' | 'error'

/** `GET /status`. */
export interface ILiveStatus {
  state: LiveState
  reachable: boolean
  /** Codice `worldlive.*` del motivo se non connesso. */
  code: string | null
  protocol: number | null
  mud: Record<string, unknown>
  /** Classi di comandi attive (`read`, `write`). */
  classes: string[]
  commands: string[]
  features: string[]
  /** Campi accettati da `player.set` (vuoto se le scritture sono disattivate nel MUD). */
  editableFields: string[]
  latencyMs: number | null
}

/** Un giocatore connesso. */
export interface ILiveWhoPlayer {
  name: string
  state: string
  level: number | null
  levels: Record<string, number>
  race: number | null
  sex: number | null
  room: number | null
  zone: number | null
  position: number | null
  fighting: boolean
  idle: number | null
  immortal: boolean
  invisible: number
}

/** `GET /who`. */
export interface ILiveWho {
  players: ILiveWhoPlayer[]
  count: number
  truncated: boolean
}

/** `GET /info`. */
export interface ILiveInfo {
  mud: Record<string, unknown>
  startedAt: number | null
  now: number | null
  uptimeS: number | null
  pulse: number | null
  ticks: number | null
  lagUs: number | null
  players: Record<string, number>
  world: Record<string, number>
}

/** Una zona come la vede il gioco (`index` è quello da passare al reset). */
export interface ILiveZone {
  index: number
  num: number | null
  name: string
  top: number | null
  lifespan: number | null
  age: number | null
  resetMode: number | null
  started: boolean | null
}

/** `GET /players/{name}`: valori correnti in memoria. */
export interface ILivePlayerState {
  name: string
  state: string
  fields: Record<string, unknown>
  editableFields: string[]
}

/** Corpo di `PATCH /players/{name}`. */
export interface ILivePlayerSet {
  fields: Record<string, unknown>
  save: boolean
  confirmImmortal: boolean
}

/** Esito di `PATCH /players/{name}`. */
export interface ILivePlayerSetResult {
  name: string
  applied: Record<string, { old: unknown; new: unknown }>
  saved: boolean
  warnings: string[]
}

/** Destinazione di mob/oggetti: una stanza o un giocatore. */
export interface ILiveLoad {
  vnum: number
  room?: number | undefined
  player?: string | undefined
  count: number
  notify: boolean
}

/** Destinazione di un messaggio: una sola tra `all`, `player`, `room`. */
export interface ILiveEcho {
  text: string
  all?: boolean | undefined
  player?: string | undefined
  room?: number | undefined
}
