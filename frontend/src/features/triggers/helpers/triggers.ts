import type { ICondition, ITrigger, TAction, TriggerOwner } from '../types/triggers'

/** Gli eventi ammessi per chi possiede il trigger (come `OWNER_TYPES` del gioco). */
export const TRIGGER_TYPES: Record<TriggerOwner, readonly string[]> = {
  mob: ['speech', 'greet', 'give', 'random', 'death', 'fight', 'hitprcnt', 'act', 'tell', 'bribe', 'all_greet', 'entry', 'command'],
  object: ['get', 'drop', 'wear', 'give', 'random'],
  room: ['enter', 'exit', 'speech', 'random'],
}

/** Le uniche azioni di oggetti e stanze. */
export const ROOM_VERBS = ['mpecho', 'mpechoat', 'mpechoaround'] as const

/** I comandi MP veri: solo per i mob, con la sintassi (suggerimento nell'editor). */
export const MP_USAGE: Record<string, string> = {
  mptransfer: 'mptransfer <chi> <vnum stanza>',
  mpgoto: 'mpgoto <vnum stanza>',
  mpat: 'mpat <vnum stanza> <comando>',
  mpload: 'mpload mob <vnum> | mpload obj <vnum> [inv]',
  mppurge: 'mppurge [self|nome]',
  mpkill: 'mpkill <chi>',
  mpforce: 'mpforce <mob> <comando>',
  mpset: 'mpset <nome> <valore>',
  mpunset: 'mpunset <nome>',
  mpadd: 'mpadd <nome> <numero>',
}

/** I comandi MP che richiedono un corpo: oggetti e stanze non li usano (né `mppurge self`). */
export const MOB_ONLY_MP = ['mpgoto', 'mpkill', 'mpforce'] as const

/**
 * La sintassi del comando MP con cui inizia l'azione (`undefined` se non lo è).
 * @param text la riga di azione
 */
export function mpUsage(text: string): string | undefined {
  return MP_USAGE[text.trim().split(/\s+/)[0] ?? '']
}

/** Quanti `if` possono stare uno dentro l'altro. */
export const MAX_IF_DEPTH = 3

/** Un confronto numerico di una condizione (`10`, `>= 10`): come `CMP` del gioco. */
const CMP = /^\s*(==|!=|<=|>=|<|>)?\s*(-?\d+)\s*$/

/**
 * `true` se `level`/`hp` è un numero o un confronto valido.
 * @param value testo o numero della condizione
 */
export function validCompare(value: unknown): boolean {
  return CMP.test(String(value ?? ''))
}

/**
 * `true` se `time` è un'ora (0-23), numero o confronto.
 * @param value testo o numero della condizione
 */
export function validTime(value: unknown): boolean {
  const m = CMP.exec(String(value ?? ''))
  return m !== null && Number(m[2]) >= 0 && Number(m[2]) <= 23
}

/**
 * `true` se il comando è ammesso a oggetti e stanze: mpecho*, mptransfer, mpat, mpload, mppurge (non `self`), mpset, mpunset, mpadd.
 * @param text la riga di azione
 */
export function isRoomVerb(text: string): boolean {
  const [verb = '', arg = ''] = text.trim().split(/\s+/)
  if ((ROOM_VERBS as readonly string[]).includes(verb)) return true
  return verb in MP_USAGE && !(MOB_ONLY_MP as readonly string[]).includes(verb) && !(verb === 'mppurge' && arg === 'self')
}

/**
 * Quanti `if` stanno uno dentro l'altro, al massimo.
 * @param actions le azioni
 */
export function ifDepth(actions: TAction[]): number {
  return Math.max(0, ...actions.map((a) => (typeof a === 'string' ? 0 : 1 + ifDepth([...a.then, ...(a.else ?? [])]))))
}

/**
 * `true` se il trigger è completo: probabilità 1-100, argomento numerico per `hitprcnt`/`bribe`, azioni non vuote (anche nei blocchi)
 * e condizioni `level`/`hp` valide.
 * @param trigger il trigger
 */
export function triggerComplete(trigger: ITrigger): boolean {
  const number = trigger.argument.trim()
  const argOk = (trigger.type !== 'command' || trigger.argument.trim() !== '') && (!['hitprcnt', 'bribe'].includes(trigger.type) || (/^\d+$/.test(number) && Number(number) >= 1 && (trigger.type !== 'hitprcnt' || Number(number) <= 100)))
  const listOk = (list: TAction[]): boolean =>
    list.length > 0 && list.every((a) => (typeof a === 'string' ? a.trim() !== '' : condOk(a.if) && listOk(a.then) && (a.else ?? []).every((x) => listOk([x]))))
  return Number.isInteger(trigger.chance) && trigger.chance >= 1 && trigger.chance <= 100 && argOk && listOk(trigger.actions) && ifDepth(trigger.actions) <= MAX_IF_DEPTH
}

/** `true` se le verifiche numeriche di una condizione sono valide. */
function condOk(c: ICondition): boolean {
  return (c.var === undefined || Object.keys(c.var).length > 0) && [c.level, c.hp, c.vnum].every((v) => v === undefined || validCompare(v)) && (c.time === undefined || validTime(c.time)) && (c.chance === undefined || (Number.isInteger(c.chance) && c.chance >= 1 && c.chance <= 100))
}

/** Copia canonica di un'azione: niente `else` vuoto. */
function settledAction(action: TAction): TAction {
  if (typeof action === 'string') return action
  const out: TAction = { if: { ...action.if }, then: action.then.map(settledAction) }
  if (action.else?.length) out.else = action.else.map(settledAction)
  return out
}

/**
 * Normalizza il valore di `extra.triggers` / `extra.scripts` (lista di trigger, `[]` se assente o non valido).
 * @param value valore grezzo
 * @returns i trigger con tutti i campi
 */
export function settledTriggers(value: unknown): ITrigger[] {
  if (!Array.isArray(value)) return []
  return (value as ITrigger[]).map((x) => ({
    type: x.type,
    argument: x.argument ?? '',
    ...(x.block ? { block: true } : {}),
    chance: x.chance ?? 100,
    actions: (x.actions ?? []).map(settledAction),
  }))
}

/**
 * L'indice (0-based) del trigger a cui si riferisce un problema di `content.validate` («..., trigger 2: il comando ...»).
 * @param message messaggio del problema
 * @returns l'indice, `-1` se il messaggio non lo riporta
 */
export function triggerIndexOf(message: string): number {
  const found = /trigger (\d+)/.exec(message)
  return found ? Number(found[1]) : -1
}
