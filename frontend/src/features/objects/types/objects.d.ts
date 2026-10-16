/** Opzione `{ value, label }` restituita da `GET /api/meta/enums`. */
export interface IEnumOption {
  value: number
  label: string
}

/** Enum del backend usati dal form degli oggetti. */
export interface IObjectEnums {
  objectType: IEnumOption[]
  /** Bersagli degli affects (`BuffTarget`): non ancora esposto da `/api/meta/enums`, quindi opzionale. */
  buffTarget?: IBuffTargetOption[]
}

/** Opzione di bersaglio affect: `value` è la chiave usata nel dizionario `affects` (nome o intero). */
export interface IBuffTargetOption {
  value: string | number
  label: string
}

/** Zona (solo i campi usati dal selettore). */
export interface IZoneRef {
  id: number
  vnum: number
  name: string
}

/** Uso di un prototipo in un comando di reset (`GET /api/objects/{id}/usage`). */
export interface IResetUsage {
  zoneId: number
  zoneName: string
  resetCommandId: number
  orderIndex: number
  commandType: number
}

/** Prototipo di oggetto (camelCase come da contratto backend). */
export interface IObjects {
  id: number
  vnum: number
  zoneId: number
  keywords: string
  shortDescription: string
  longDescription: string
  actionDescription: string | null
  objectType: number
  weight: number
  cost: number
  rent: number
  value0: number | null
  value1: number | null
  value2: number | null
  value3: number | null
  extraFlags: string[]
  wearFlags: string[]
  affects: Record<string, number>
  /** Campi specifici del mondo (vuoto in pachimud); in scrittura solo le chiavi cambiate. */
  extra?: Record<string, unknown>
}

/** Corpo di creazione/modifica (senza `id`). */
export type IObjectsInput = Omit<IObjects, 'id'>

export interface IPaginatedObjects {
  items: IObjects[]
  total: number
  page?: number
  pageSize?: number
  pages?: number
}
