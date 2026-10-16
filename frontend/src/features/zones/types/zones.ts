/** Opzione di enum come restituita da `GET /api/meta/enums`. */
export interface IEnumOption {
  value: number
  label: string
}

/** Enum del backend usati dal modulo zone (sottoinsieme di `GET /api/meta/enums`). */
export interface IZoneEnums {
  zoneResetMode: IEnumOption[]
  zoneCommandType: IEnumOption[]
  direction: IEnumOption[]
}

/** Una zona (`ZoneOut`). */
export interface IZone {
  id: number
  vnum: number
  name: string
  builder: string
  bottomVnum: number
  topVnum: number
  minLevel: number
  maxLevel: number
  lifespanMinutes: number
  resetMode: number
  enabled: boolean
  /** Campi specifici del mondo (vuoto in pachimud); in scrittura solo le chiavi cambiate. */
  extra?: Record<string, unknown>
}

/** Dati per creare/modificare una zona (`ZoneIn`/`ZonePatch`). */
export type IZoneInput = Omit<IZone, 'id'>

/** Risposta di `GET /api/zones/next-vnum`. */
export interface IZoneVnumSuggestion {
  vnum: number
  bottomVnum: number
  topVnum: number
}

/** Corpo di `POST /api/zones/{id}/clone`. */
export interface IZoneCloneInput {
  vnum: number
  name: string
  copyResetCommands: boolean
}

/** Un passo dello script di reset come restituito dal backend (`ResetCommandOut`). */
export interface IResetCommand {
  id: number
  zoneId: number
  orderIndex: number
  commandType: number
  ifFlag: boolean
  arg1: number | null
  arg2: number | null
  arg3: number | null
  arg4: number | null
  argStr: string | null
  /** `if_flag` come intero (mondi che lo dichiarano, es. Diku Modificato: `> 0` condizionato, `<= 0` sempre, anche -5). */
  ifValue?: number | null
  /** Commento della riga (mondi che lo dichiarano). */
  comment?: string | null
  /** Campi specifici del mondo del comando (es. `letter`); non inviati. */
  extra?: Record<string, unknown>
}

/** Un passo dello script di reset come inviato al backend (`ResetCommandIn`). */
export type IResetCommandInput = Omit<IResetCommand, 'id' | 'zoneId' | 'orderIndex' | 'extra'>

/** Tipo di contenuto referenziato da un argomento vnum di un passo di reset. */
export type TLookupKind = 'room' | 'mob' | 'object'

/** Vnum noti per tipo di contenuto, con il nome da mostrare come suggerimento. */
export type ILookups = Record<TLookupKind, Map<number, string>>

/**
 * Problema segnalato sullo script di reset (errore di salvataggio o esito di "Valida").
 * `index` è 0-based; `null` se il problema riguarda lo script nel suo insieme.
 */
export interface IResetIssue {
  index: number | null
  level: 'error' | 'warning'
  /** Testo già tradotto (da `errors.codes.<code>` o, in mancanza, dal messaggio del backend). */
  text: string
  code?: string
  params?: Record<string, string | number>
}
