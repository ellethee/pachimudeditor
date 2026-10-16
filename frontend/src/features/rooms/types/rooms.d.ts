/** Tipi della feature rooms (contratto backend: docs/backend/contract.md, camelCase). */

/** Risposta paginata del backend. */
export interface IPaginatedRooms<T = IRoom> {
  items: T[]
  total: number
  page: number
  pageSize: number
  pages: number
}

/** Opzione di enum restituita da `GET /api/meta/enums`. */
export interface IEnumOption {
  value: number
  label: string
}

/** Enum del backend usati dalle stanze. */
export interface IEnumOptions {
  sectorType: IEnumOption[]
  direction: IEnumOption[]
  doorFlag: IEnumOption[]
}

/** Zona (solo i campi usati per il selettore). */
export interface IZoneRef {
  id: number
  vnum: number
  name: string
}

/** Stanza (riga di lista). */
export interface IRoom {
  id: number
  vnum: number
  zoneId: number
  name: string
  description: string
  sectorType: number
  flags: string[]
  healRate: number
  manaRate: number
  clanId: string | null
  owner: string | null
  /** Campi specifici del mondo (vuoto in pachimud); in scrittura solo le chiavi cambiate. */
  extra?: Record<string, unknown>
}

/** Payload di creazione/aggiornamento stanza. */
export type IRoomInput = Omit<IRoom, 'id'>

/** Uscita di una stanza. */
export interface IRoomExit {
  id: number
  roomId: number
  direction: number
  description: string | null
  keywords: string | null
  doorFlag: number
  isOpen: boolean
  isLocked: boolean
  keyVnum: number | null
  targetRoomId: number | null
  targetRoomVnum: number | null
  targetRoomName: string | null
  /** Campi specifici del mondo dell'uscita (vuoto in pachimud). */
  extra?: Record<string, unknown>
}

/** Payload di creazione/aggiornamento uscita. */
export type IRoomExitInput = Omit<IRoomExit, 'id' | 'roomId' | 'targetRoomVnum' | 'targetRoomName'>

/** Extra description di una stanza. */
export interface IExtraDescription {
  id: number
  roomId: number
  keywords: string
  text: string
}

/** Payload di creazione/aggiornamento extra description. */
export type IExtraDescriptionInput = Omit<IExtraDescription, 'id' | 'roomId'>

/** Dettaglio stanza con uscite ed extra description. */
export interface IRoomDetail extends IRoom {
  exits: IRoomExit[]
  extraDescriptions: IExtraDescription[]
}

/** Uso di una stanza in un comando di reset. */
export interface IResetUsage {
  zoneId: number
  zoneName: string
  resetCommandId: number
  orderIndex: number
  commandType: number | string
}

/** Nodo del grafo delle stanze. */
export interface IGraphNode {
  id: number
  vnum: number
  name: string
  sectorType: number
  flags: string[]
  x: number
  y: number
  danglingExits: number
}

/** Arco del grafo delle stanze. */
export interface IGraphEdge {
  id: number
  fromRoomId: number
  toRoomId: number
  direction: number
  doorFlag: number
  twoWay: boolean
  reverseExitId: number | null
}

/** Grafo di una zona. */
export interface IRoomGraph {
  nodes: IGraphNode[]
  edges: IGraphEdge[]
}

/** Riga di editor per una direzione di uscita. */
export interface IExitRow {
  direction: number
  hasExit: boolean
  description: string | null
  keywords: string | null
  doorFlag: number
  isOpen: boolean
  isLocked: boolean
  keyVnum: number | null
  targetRoomId: number | null
  /** Valori correnti dei campi `extra` dell'uscita (modificabili dal form). */
  extra?: Record<string, unknown>
}

/** Extra description in editing (`uid` stabile lato client). */
export interface IExtraRow {
  uid: string
  keywords: string
  text: string
}

/** Opzione di stanza per le select di destinazione. */
export interface IRoomOption {
  id: number
  label: string
}
