/** Tipi della feature world (contratto backend: docs/backend/contract-world.md, camelCase). */

/** Tipo di entità dell'editor. */
export type WorldEntityType = 'zone' | 'room' | 'mob' | 'object'

/** Conteggi globali del mondo. */
export interface IWorldCounts {
  zones: number
  zonesEnabled: number
  zonesDisabled: number
  rooms: number
  mobs: number
  objects: number
  mobInstances: number
  objectInstances: number
  accounts: number
  characters: number
}

/** Riga di riepilogo per zona. */
export interface IZoneOverview {
  id: number
  vnum: number
  name: string
  enabled: boolean
  bottomVnum: number
  topVnum: number
  rooms: number
  mobs: number
  objects: number
  /** Percentuale di range occupata; `null` se il range è 0-0 (da assegnare). */
  rangeUsagePct: number | null
  resetCommands: number
}

/** Tipi di warning di qualità dei dati. */
export type WarningKind =
  | 'room_empty_description'
  | 'exit_without_target'
  | 'zone_empty_reset_script'
  | 'vnum_out_of_range'
  | 'mob_never_loaded'
  | 'object_never_loaded'

/** Un warning di qualità dei dati. */
export interface IQualityWarning {
  kind: WarningKind
  entityType: WorldEntityType
  entityId: number
  vnum: number
  name: string
  zoneId: number
  zoneName: string
  params: Record<string, number>
}

/** Risposta di `GET /world/overview`. */
export interface IWorldOverview {
  counts: IWorldCounts
  zones: IZoneOverview[]
  warnings: IQualityWarning[]
  warningTotals: Partial<Record<WarningKind, number>>
}

/** Nodo del grafo tra zone. */
export interface IZoneGraphNode {
  id: number
  vnum: number
  name: string
  enabled: boolean
  rooms: number
  isolated: boolean
}

/** Arco orientato tra zone (numero di uscite). */
export interface IZoneGraphEdge {
  fromZoneId: number
  toZoneId: number
  count: number
}

/** Risposta di `GET /world/zone-graph`. */
export interface IZoneGraph {
  nodes: IZoneGraphNode[]
  edges: IZoneGraphEdge[]
}

/** Risultato di ricerca. */
export interface ISearchHit {
  id: number
  vnum: number
  name: string
  keywords: string | null
  zoneId: number
  zoneName: string
}

/** Risultati di un tipo. */
export interface ISearchGroup {
  items: ISearchHit[]
  total: number
}

/** Risposta di `GET /world/search`. */
export interface ISearchResults {
  q: string
  zones: ISearchGroup
  rooms: ISearchGroup
  mobs: ISearchGroup
  objects: ISearchGroup
}

/** Range di vnum libero. */
export interface IZoneRange {
  bottomVnum: number
  topVnum: number
}
