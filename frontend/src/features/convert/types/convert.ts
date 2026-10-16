/** Mondo configurato (`GET /api/convert/pairs`). */
export interface IWorldRef {
  id: string
  kind: string
  name: string
  readOnly: boolean
}

/** Coppia ordinata sorgente/arrivo. */
export interface IPairInfo {
  source: string
  target: string
  sourceKind: string
  targetKind: string
  converter: 'specific' | 'generic'
  allowed: boolean
  reason: 'same_world' | 'target_read_only' | null
}

/** Risposta di `GET /api/convert/pairs`. */
export interface IPairs {
  worlds: IWorldRef[]
  pairs: IPairInfo[]
  journalEnabled: boolean
}

/** Zona di un mondo (campi usati dalla pagina). */
export interface IZoneRef {
  id: number
  vnum: number
  name: string
  bottomVnum: number
  topVnum: number
}

export type VnumMode = 'keep' | 'offset' | 'shift_to'

/** Corpo di `POST /api/convert/preview` e `/run`. */
export interface IConvertRequest {
  sourceWorld: string
  targetWorld: string
  zoneIds: number[]
  vnumPolicy: { mode: VnumMode; offset: number }
  onConflict: 'skip' | 'replace'
  convertResets: boolean
  convertExits: boolean
  convertExtraDescriptions: boolean
  dryRun: boolean
  confirm: boolean
}

export type Severity = 'info' | 'warning' | 'dropped'

/** Una perdita (o approssimazione) della conversione. */
export interface ILossItem {
  entity: string
  vnum: number | null
  zoneVnum: number | null
  index: number | null
  field: string
  code: string
  params: Record<string, string | number>
  severity: Severity
  message: string
}

export interface IEntityCounts {
  create: number
  replace: number
  skip: number
  dropped: number
}

export interface IZoneAction {
  sourceZoneId: number
  sourceVnum: number
  name: string
  action: 'create' | 'replace' | 'skip' | 'blocked'
  targetVnum: number
  targetZoneId: number | null
  sourceBottomVnum: number
  sourceTopVnum: number
  bottomVnum: number
  topVnum: number
  offset: number
  counts: Record<string, number>
}

export interface IConflict {
  zoneVnum: number
  kind: 'zone_exists' | 'range_overlap' | 'vnum_taken'
  entity: string | null
  vnum: number | null
  otherZone: string | null
  resolved: boolean
}

export interface IReportError {
  code: string
  params: Record<string, string | number>
  message: string
}

/** Rapporto di una conversione (anteprima o esecuzione). */
export interface IConvertReport {
  dryRun: boolean
  applied: boolean
  sourceWorld: string
  targetWorld: string
  sourceKind: string
  targetKind: string
  converter: 'specific' | 'generic'
  zones: IZoneAction[]
  totals: Record<string, IEntityCounts>
  remap: Record<string, Record<string, number>>
  losses: ILossItem[]
  lossSummary: Partial<Record<Severity, number>>
  conflicts: IConflict[]
  errors: IReportError[]
  rolledBack: boolean
  rollbackErrors: IReportError[]
  journal: { enabled: boolean; file: string | null }
}
