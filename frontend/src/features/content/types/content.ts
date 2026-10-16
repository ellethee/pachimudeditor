/** Caratteristiche di un personaggio (`Stats` del gioco). */
export interface IStats {
  strength: number
  dexterity: number
  constitution: number
  intelligence: number
  wisdom: number
  charisma: number
}

/** Tipo di contenuto gestito: razze o classi. */
export type ContentKind = 'races' | 'classes'

/** Una razza (`RaceItem`): campi del file YAML + metadati. */
export interface IRace {
  raceId: string
  name: string
  description: string
  mobOnly: boolean | null
  whoName: string | null
  points: number | null
  size: string | null
  startRoom: number | null
  extraTrainingCap: number | null
  mobFlags: string[] | null
  offensiveFlags: string[] | null
  immunity: string[] | null
  resistance: string[] | null
  vulnerability: string[] | null
  form: string[] | null
  parts: string[] | null
  affectedBy: string[] | null
  skills: string[] | null
  stats: IStats | null
  maxStats: IStats | null
  /** Nome del file (`human.yaml` o `human.yaml.disabled`). */
  file: string
  disabled: boolean
  /** Prototipi di mob che usano la razza. */
  mobCount: number
  valid: boolean
  error: string | null
}

/** Una classe (`ClassItem`). I nomi `thac000`/`thac032` sono gli alias camelCase di `thac0_00`/`thac0_32`. */
export interface IClass {
  classId: string
  name: string
  description: string
  abbreviation: string
  addStrength: boolean | null
  attrsPriority: string[]
  attrPrime: string
  thac000: number
  thac032: number
  hpMin: number
  hpMax: number
  weapon: number
  skillAdept: number
  file: string
  disabled: boolean
  mobCount: number
  valid: boolean
  error: string | null
}

/** Elemento generico di tabella (razza o classe) con le sole colonne comuni. */
export type IContentItem = IRace | IClass

/** Valori ammessi per i campi dei form (`GET /api/content/options`). */
export interface IContentOptions {
  mobFlags: string[]
  offensiveFlags: string[]
  resistanceFlags: string[]
  formFlags: string[]
  partFlags: string[]
  affectedByFlags: string[]
  sizes: string[]
  stats: string[]
}

/** Stato dei contenuti (`GET /api/content/status`). */
export interface IContentStatus {
  races: number
  classes: number
  /** Epoch (secondi) dell'ultima modifica di un file, o `null` se non ci sono file. */
  lastModified: number | null
}
