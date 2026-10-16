import type { ILookups, IResetCommandInput, IZoneEnums, TLookupKind } from '../types/zones'

/** Stati possibili di una porta per il comando SET_DOOR_STATE. */
export const DOOR_STATES = ['OPEN', 'CLOSED', 'LOCKED'] as const

/** Valori numerici di `zoneCommandType` (ROM: M/O/G/E/P/D/R; Diku Modificato aggiunge 7-10: C/H/F/Z). */
export const CommandType = {
  LOAD_MOB: 0,
  LOAD_OBJECT: 1,
  GIVE_OBJECT: 2,
  EQUIP_OBJECT: 3,
  PUT_OBJECT: 4,
  SET_DOOR_STATE: 5,
  RANDOMIZE_EXITS: 6,
  CHARM_MOB: 7,
  SET_HATE: 8,
  SET_FEAR: 9,
  SET_MOB_ZONE: 10,
} as const

/** Argomento numerico che referenzia un vnum: chiave i18n dell'etichetta e tipo di contenuto atteso. */
export interface IVnumArgSpec {
  labelKey: string
  /** Contenuto referenziato; `null` = numero semplice senza controllo del vnum. */
  kind: TLookupKind | null
}

/** Quali campi mostrare per un tipo di comando e con quale forma. */
export interface ICommandSpec {
  arg1?: IVnumArgSpec
  arg2?: 'number' | 'direction'
  /** Etichetta di arg2 (numero) al posto di "max esistenti". */
  arg2LabelKey?: string
  arg3?: IVnumArgSpec
  /** Etichetta di arg4 (numero semplice). */
  arg4LabelKey?: string
  argStr?: 'text' | 'doorState'
}

/**
 * Descrive i campi di ogni comando di reset (vedi i comandi M/O/G/E/P/D/R di ROM).
 * @param commandType valore di `zoneCommandType`
 * @returns la specifica dei campi; vuota per tipi sconosciuti
 */
export function specFor(commandType: number): ICommandSpec {
  const mob: IVnumArgSpec = { labelKey: 'zones.resets.args.mobVnum', kind: 'mob' }
  const obj: IVnumArgSpec = { labelKey: 'zones.resets.args.objectVnum', kind: 'object' }
  const room: IVnumArgSpec = { labelKey: 'zones.resets.args.roomVnum', kind: 'room' }
  switch (commandType) {
    case CommandType.LOAD_MOB:
      return { arg1: mob, arg2: 'number', arg3: room, arg4LabelKey: 'zones.resets.args.roomLimit' }
    case CommandType.LOAD_OBJECT:
      return { arg1: obj, arg2: 'number', arg3: room, arg4LabelKey: 'zones.resets.args.roomLimit' }
    case CommandType.GIVE_OBJECT:
      return { arg1: obj, arg2: 'number' }
    case CommandType.EQUIP_OBJECT:
      return { arg1: obj, arg2: 'number', argStr: 'text' }
    case CommandType.PUT_OBJECT:
      return {
        arg1: obj,
        arg2: 'number',
        arg3: { labelKey: 'zones.resets.args.containerVnum', kind: 'object' },
      }
    case CommandType.SET_DOOR_STATE:
      return { arg1: room, arg2: 'direction', argStr: 'doorState' }
    case CommandType.RANDOMIZE_EXITS:
      return { arg1: room }
    case CommandType.CHARM_MOB:
      return { arg1: mob, arg2: 'number', arg3: { labelKey: 'zones.resets.args.actBit', kind: null } }
    case CommandType.SET_HATE:
    case CommandType.SET_FEAR:
      return {
        arg1: { labelKey: 'zones.resets.args.hateType', kind: null },
        arg2: 'number',
        arg2LabelKey: 'zones.resets.args.hateValue',
      }
    case CommandType.SET_MOB_ZONE:
      return {
        arg1: { labelKey: 'zones.resets.args.zoneVnum', kind: null },
        arg2: 'number',
        arg2LabelKey: 'zones.resets.args.zoneFlag',
      }
    default:
      return {}
  }
}

/**
 * Converte il valore di un `q-input` numerico in `number | null` (la stringa vuota diventa `null`).
 * @param value valore emesso dall'input
 */
export function toNumberOrNull(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Nome dell'elemento referenziato da un argomento, se il vnum è noto.
 * @param spec specifica dell'argomento
 * @param value vnum inserito
 * @param lookups vnum noti
 */
export function lookupName(
  spec: IVnumArgSpec | undefined,
  value: number | null,
  lookups: ILookups,
): string | undefined {
  if (!spec?.kind || value === null) return undefined
  return lookups[spec.kind].get(value)
}

/**
 * Indica se l'argomento referenzia un vnum inesistente.
 * @param spec specifica dell'argomento
 * @param value vnum inserito
 * @param lookups vnum noti
 */
export function isUnknownVnum(
  spec: IVnumArgSpec | undefined,
  value: number | null,
  lookups: ILookups,
): boolean {
  return !!spec?.kind && value !== null && !lookups[spec.kind].has(value)
}

/**
 * Indica se un passo referenzia almeno un vnum inesistente (arg1 o arg3).
 * @param row passo di reset
 * @param lookups vnum noti
 */
export function rowHasUnknownVnum(row: IResetCommandInput, lookups: ILookups): boolean {
  const spec = specFor(row.commandType)
  return isUnknownVnum(spec.arg1, row.arg1, lookups) || isUnknownVnum(spec.arg3, row.arg3, lookups)
}

/**
 * Etichetta del tipo di comando presa dagli enum del backend.
 * @param enums enum caricati (o null)
 * @param commandType valore del tipo
 */
export function commandTypeLabel(enums: IZoneEnums | null, commandType: number): string {
  return enums?.zoneCommandType.find((option) => option.value === commandType)?.label ?? String(commandType)
}

/**
 * Riepilogo breve di un passo, mostrato nell'intestazione.
 * @param row passo di reset
 */
export function summarize(row: IResetCommandInput): string {
  const spec = specFor(row.commandType)
  const parts: string[] = []
  if (spec.arg1 && row.arg1 !== null) parts.push(`vnum ${row.arg1}`)
  if (spec.arg3 && row.arg3 !== null) parts.push(`-> ${row.arg3}`)
  if (spec.argStr && row.argStr) parts.push(row.argStr)
  return parts.join(' ') || '—'
}

/**
 * Passo vuoto del tipo indicato.
 * @param commandType tipo di comando iniziale
 */
export function emptyCommand(commandType: number): IResetCommandInput {
  return {
    commandType,
    ifFlag: false,
    arg1: null,
    arg2: null,
    arg3: null,
    arg4: null,
    argStr: commandType === CommandType.SET_DOOR_STATE ? 'CLOSED' : null,
  }
}

/**
 * Indica se un passo ha ancora vuoti degli argomenti obbligatori per il suo tipo
 * (arg1/arg2/arg3/argStr secondo `specFor`; `arg4` e' sempre opzionale).
 * @param row passo di reset
 */
export function isIncomplete(row: IResetCommandInput): boolean {
  const spec = specFor(row.commandType)
  return (
    (!!spec.arg1 && row.arg1 === null) ||
    (!!spec.arg2 && row.arg2 === null) ||
    (!!spec.arg3 && row.arg3 === null) ||
    (!!spec.argStr && !row.argStr)
  )
}
