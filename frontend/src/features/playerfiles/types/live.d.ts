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
  /** Numero (dikumod) o id stringa (pachimud). */
  race: number | string | null
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
  bottom?: number | null
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

/** Esito di `POST /load/mob|obj`: `warnings` può contenere `vnum_not_saveable` (oggetto > 32767 a un giocatore). */
export interface ILiveLoadResult {
  loaded: Record<string, unknown>[]
  warnings: string[]
}

/** Affect di un oggetto istanza (`location` 0 = nessuno). */
export interface ILiveItemAffect {
  location: number
  modifier: number
}

/** Oggetto istanza di un giocatore connesso (`ref` e `fp` sono opachi: si rimandano così come sono). */
export interface ILiveItem {
  ref: string
  fp: string
  vnum: number | null
  slot: number | null
  depth: number
  name: string
  shortDescription: string
  type: number | null
  contents: number
  description: string | null
  values: number[]
  weight: number | null
  extraFlags: number | null
  timer: number | null
  affects: ILiveItemAffect[]
  /** Solo `GET .../inventory/item` (sola lettura). */
  wearFlags?: number | null
  cost?: number | null
  costPerDay?: number | null
  bitvector?: number | null
}

/** `GET /players/{name}/inventory`: elenco piatto in preordine (`depth` per l'annidamento). */
export interface ILiveInventory {
  name: string
  carryWeight: number
  carryItems: number
  count: number
  truncated: boolean
  items: ILiveItem[]
}

/** Controllo di modifica concorrente: valori dell'ultima lettura. */
export interface ILiveItemExpect {
  vnum: number | null
  fp: string
}

/** Patch parziale di un oggetto (`values`/`affects`: `null` = posizione invariata). */
export interface ILiveItemChanges {
  name?: string
  shortDescription?: string
  description?: string
  values?: (number | null)[]
  weight?: number
  extraFlags?: number
  timer?: number
  affects?: (ILiveItemAffect | null)[]
}

/** Corpo di `PATCH .../inventory/item`. */
export interface ILiveItemSet {
  expect: ILiveItemExpect
  set: ILiveItemChanges
  save: boolean
}

/** Esito di `PATCH .../inventory/item`. */
export interface ILiveItemSetResult {
  name: string
  fp: string
  saved: boolean
  warnings: string[]
  item: ILiveItem | null
}

/** Esito di `DELETE .../inventory/item`. */
export interface ILiveItemRemoveResult {
  name: string
  removed: boolean
  destroyed: number
  saved: boolean
  warnings: string[]
}

/** Un'istanza in memoria (`GET /instances`, estensione pachimud). */
export interface ILiveInstance {
  instanceId: number | string
  kind: 'mob' | 'obj'
  vnum: number
  roomVnum: number | null
}

/** `GET /instances`. */
export interface ILiveInstances {
  instances: ILiveInstance[]
  count: number
  truncated: boolean
}

/** Esito di `POST /zones/reload`: conteggi dei contenuti riletti dal gioco. */
export interface ILiveZoneReload {
  zone: number
  name: string
  reloaded: boolean
  rooms: number
  mobs: number
  objects: number
}
