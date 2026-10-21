/** Tipi di `GET /api/world/players...` (vedi `docs/backend/contract-players-files.md`). */

import type { IExtraFieldDescriptor } from '../../shared/types/worlds'

/** Come si formatta il valore di una colonna. */
export type PlayerColumnType = 'text' | 'number' | 'datetime' | 'boolean' | 'duration'

/** Colonna dell'elenco dichiarata dall'adapter. */
export interface IPlayerColumn {
  name: string
  labelKey: string
  type: PlayerColumnType
  sortable: boolean
  /** `extra`: il valore sta in `extra[name]` invece che nel campo omonimo. */
  source: 'field' | 'extra'
}

/** Colonna di una tabella del dettaglio. */
export interface IPlayerListColumn {
  name: string
  labelKey: string
  type: PlayerColumnType
}

/** Tabella del dettaglio (abilità, effetti, ...). */
export interface IPlayerListInfo {
  name: string
  labelKey: string
  columns: IPlayerListColumn[]
}

/** Descrittore dei giocatori del mondo (`GET /info`). */
export interface IPlayersInfo {
  columns: IPlayerColumn[]
  detailFields: IExtraFieldDescriptor[]
  detailLists: IPlayerListInfo[]
  hasAccounts: boolean
  onlinePolicy: 'unknown' | 'warn'
  /** Slot di equipaggiamento ammessi, nell'ordine del MUD. */
  wearSlots: string[]
}

/** Stato del server di gioco (`GET /status`); `serverRunning` nullo = non rilevabile. */
export interface IPlayersStatus {
  serverRunning: boolean | null
  detection: string
}

/** Riga dell'elenco. Mai password: solo `hasPassword`. */
export interface IPlayerSummary {
  id: string
  name: string
  level: number | null
  classLabel: string | null
  raceLabel: string | null
  sex: string | null
  gold: number | null
  roomVnum: number | null
  lastLoginAt: string | null
  playedSeconds: number | null
  hasPassword: boolean | null
  online: boolean | null
  /** Codice stabile se il file è illeggibile/corrotto. */
  problem: string | null
  /** Impronta del file letto: da rimandare nelle scritture per rilevare modifiche concorrenti. */
  revision: string | null
  extra: Record<string, unknown>
}

/** Dettaglio: `details` per i campi dichiarati, `lists` per le tabelle dichiarate. */
export interface IPlayerDetail extends IPlayerSummary {
  details: Record<string, unknown>
  lists: Record<string, Record<string, unknown>[]>
}

/** Oggetto di un inventario/equipaggiamento. */
export interface IPlayerItem {
  id: number
  vnum: number | null
  name: string
  keywords: string
  wearSlot: string | null
  depth: number
  known: boolean
  extra: Record<string, unknown>
}

/** Inventario con eventuale problema di lettura. */
export interface IPlayerInventory {
  items: IPlayerItem[]
  problem: string | null
  /** Impronta del file dell'inventario. */
  revision: string | null
  extra: Record<string, unknown>
}

/** Pagina di risultati. */
export interface IPlayerPage {
  items: IPlayerSummary[]
  total: number
}

/** Opzioni comuni di ogni scrittura. */
export interface IPlayerWriteOptions {
  /** La `revision` letta (se il file è cambiato: 409 `worldplayers.conflict`). */
  revision?: string | null
  /** Obbligatoria se il server di gioco risulta acceso. */
  confirmServerRunning?: boolean
}

/** Modifica parziale del dettaglio (`PATCH /{id}`). */
export interface IPlayerPatch extends IPlayerWriteOptions {
  details?: Record<string, unknown>
  lists?: Record<string, Record<string, unknown>[]>
}

/** Aggiunta di un oggetto dal prototipo del mondo (`POST /{id}/inventory/items`). */
export interface IPlayerItemAdd extends IPlayerWriteOptions {
  vnum: number
  /** Nome dello slot, `null` = portato. */
  wearSlot?: string | null
  /** `id` del contenitore in cui metterlo. */
  containerId?: number | null
}
