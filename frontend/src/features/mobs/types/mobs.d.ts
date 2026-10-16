/** Opzione `{ value, label }` restituita da `GET /api/meta/enums`. */
export interface IEnumOption {
  value: number
  label: string
}

/** Enum del backend usati dal form dei mob. */
export interface IMobEnums {
  sex: IEnumOption[]
}

/** Riferimento a contenuto YAML (razza/classe), da `GET /api/meta/races|classes`. */
export interface IContentRef {
  id: string
  name: string
}

/** Zona (solo i campi usati dal selettore). */
export interface IZoneRef {
  id: number
  vnum: number
  name: string
}

/** Uso di un prototipo in un comando di reset (`GET /api/mobs/{id}/usage`). */
export interface IResetUsage {
  zoneId: number
  zoneName: string
  resetCommandId: number
  orderIndex: number
  commandType: number
}

/** Prototipo di mob (camelCase come da contratto backend). */
export interface IMobs {
  id: number
  vnum: number
  zoneId: number
  keywords: string
  shortDescription: string
  longDescription: string
  detailedDescription: string
  level: number
  thac0: number
  armorClass: number
  hpDiceCount: number
  hpDieSize: number
  hpBonus: number
  damageDiceCount: number
  damageDieSize: number
  damageBonus: number
  gold: number
  experience: number
  sex: number
  flags: string[]
  raceId: string | null
  classId: string | null
  alignment: number
  debuffSkillId: string | null
  shopId: string | null
  questIds: string[]
  isBanker: boolean
  teachesClassIds: string[] | null
  teachesSkillIds: string[] | null
  /** Campi specifici del mondo (vuoto in pachimud); in scrittura solo le chiavi cambiate. */
  extra?: Record<string, unknown>
}

/** Corpo di creazione/modifica (senza `id`). */
export type IMobsInput = Omit<IMobs, 'id'>

export interface IPaginatedMobs {
  items: IMobs[]
  total: number
  page?: number
  pageSize?: number
  pages?: number
}
