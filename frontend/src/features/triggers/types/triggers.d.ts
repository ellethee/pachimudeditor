/** Di chi è il trigger: determina i tipi ammessi e le azioni consentite. */
export type TriggerOwner = 'mob' | 'object' | 'room'

/** Le verifiche di un `if` (valgono tutte insieme); le chiavi sconosciute si conservano (le segnala il controllo dei contenuti). */
export interface ICondition {
  chance?: number
  level?: number | string
  hp?: number | string
  sex?: 'male' | 'female' | 'other'
  race?: string
  class?: string
  carries?: string
  is_player?: boolean
  time?: number | string
  is_night?: boolean
  is_fighting?: boolean
  has_effect?: string
  vnum?: number | string
  /** Variabili di stato (`mpset`): nome -> valore o confronto numerico. */
  var?: Record<string, string>
  who?: 'n' | 'i'
  [unknown: string]: unknown
}

/** Un blocco `if`/`then`/`else`. */
export interface IIfBlock {
  if: ICondition
  then: TAction[]
  else?: TAction[]
}

/** Un'azione: un comando o un blocco `if`. */
export type TAction = string | IIfBlock

/** Un trigger di un mob, o uno script di un oggetto / un trigger di una stanza (pachimud). */
export interface ITrigger {
  type: string
  /** Vuoto = qualsiasi. */
  argument: string
  /** Solo `command`: il comando del giocatore non viene eseguito. */
  block?: boolean
  /** 1-100. */
  chance: number
  actions: TAction[]
}
