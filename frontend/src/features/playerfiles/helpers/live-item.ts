import { computed } from 'vue'
import { useWorld } from '../../shared/helpers/world-state'
import type { ILiveItem, ILiveItemAffect, ILiveItemChanges } from '../types/live'

/** Vnum massimo del rent di un gioco non modificato: lo salva in uno `short`. */
export const MAX_RENT_VNUM = 32767

/**
 * Vnum massimo che il file del giocatore (rent) del mondo attivo può contenere: 32767 (`short`) o, con la patch del gioco
 * (`params.rent_vnum: unsigned`), 65535.
 *
 * @returns valore reattivo
 */
export function useMaxRentVnum() {
  const { activeWorld } = useWorld()
  return computed(() => {
    const max = activeWorld.value?.params?.rent_vnum_max
    return typeof max === 'number' && max > 0 ? max : MAX_RENT_VNUM
  })
}
/** Valore di `timer` che significa «nessun timer». */
export const NO_TIMER = -7000000
/** Limiti dei testi di un oggetto istanza, in byte latin-1 (record di rent del gioco). */
export const TEXT_LIMITS = { name: 127, shortDescription: 127, description: 255 } as const

/** Opzione di enum di `/api/meta/enums`. */
export interface IEnumOpt {
  value: number
  label: string
}

/**
 * Controlla un testo di oggetto come farà il MUD: non vuoto, entro il limite, latin-1, senza `$`, `~` e caratteri di controllo.
 *
 * @param text - testo digitato
 * @param max - lunghezza massima in byte
 * @returns chiave i18n (sotto `playerFiles.liveInv.textError`) del problema, oppure `null` se valido
 */
export function textProblem(text: string, max: number): 'empty' | 'long' | 'chars' | null {
  if (text.length === 0) return 'empty'
  if (text.length > max) return 'long'
  // eslint-disable-next-line no-control-regex
  return /[\u0000-\u001f\u007f$~]|[^\u0000-ÿ]/.test(text) ? 'chars' : null
}

/**
 * Maschera di flag → valori delle opzioni attive.
 *
 * @param mask - maschera di bit
 * @param options - opzioni con `value` = bit
 */
export function flagsToList(mask: number, options: IEnumOpt[]): number[] {
  return options.filter((o) => o.value !== 0 && (mask & o.value) === o.value).map((o) => o.value)
}

/**
 * Valori delle opzioni attive → maschera, mantenendo i bit non descritti dalle opzioni (non si perdono scrivendo).
 *
 * @param list - bit scelti
 * @param base - maschera letta
 * @param options - opzioni note
 */
export function listToFlags(list: number[], base: number, options: IEnumOpt[]): number {
  const known = options.reduce((acc, o) => acc | o.value, 0)
  return list.reduce((acc, v) => acc | v, base & ~known) >>> 0
}

/** Nomi dei tipi oggetto di Diku Modificato nell'ordine del gioco (indice = `type`). */
const ITEM_TYPES = [
  'none', 'light', 'scroll', 'wand', 'staff', 'weapon', 'fireweapon', 'missile', 'treasure', 'armor', 'potion', 'worn', 'other', 'trash',
  'trap', 'container', 'note', 'drinkcon', 'key', 'food', 'money', 'pen', 'boat', 'audio', 'board', 'tree', 'rock',
] // prettier-ignore

/** Significato dei 4 valori per tipo: chiave di `playerFiles.liveInv.valueLabel.<chiave>` oppure `null` (= «valore N»). */
const VALUE_LABELS: Record<string, (string | null)[]> = {
  light: [null, null, 'hours', null],
  scroll: ['level', 'spell', 'spell', 'spell'],
  potion: ['level', 'spell', 'spell', 'spell'],
  wand: ['level', 'maxCharges', 'charges', 'spell'],
  staff: ['level', 'maxCharges', 'charges', 'spell'],
  weapon: [null, 'diceNumber', 'diceSize', 'hitType'],
  armor: ['armorClass', null, null, null],
  container: ['capacity', 'lockFlags', 'keyVnum', null],
  drinkcon: ['capacity', 'current', 'liquid', 'poisoned'],
  food: ['feedHours', null, null, 'poisoned'],
  money: ['coins', null, null, null],
}

/**
 * Chiave del significato di un valore per il tipo dell'oggetto.
 *
 * @param type - tipo dell'oggetto (indice di `ITEM_TYPES`)
 * @param index - posizione del valore (0..3)
 * @returns chiave sotto `playerFiles.liveInv.valueLabel` oppure `null` se generico
 */
export function valueLabelKey(type: number | null, index: number): string | null {
  const name = type === null ? undefined : ITEM_TYPES[type]
  return (name ? VALUE_LABELS[name]?.[index] : null) ?? null
}

/** Stato modificabile di un oggetto nel dialogo (copia dei campi della lettura). */
export interface IItemDraft {
  name: string
  shortDescription: string
  description: string
  values: number[]
  weight: number
  extraFlags: number
  timer: number
  affects: ILiveItemAffect[]
}

/**
 * Copia modificabile di un oggetto letto.
 *
 * @param item - oggetto dalla lettura
 */
export function draftOf(item: ILiveItem): IItemDraft {
  const affects = Array.from({ length: 5 }, (_, i) => ({ ...(item.affects[i] ?? { location: 0, modifier: 0 }) }))
  return {
    name: item.name,
    shortDescription: item.shortDescription,
    description: item.description ?? '',
    values: Array.from({ length: 4 }, (_, i) => item.values[i] ?? 0),
    weight: item.weight ?? 0,
    extraFlags: item.extraFlags ?? 0,
    timer: item.timer ?? 0,
    affects,
  }
}

/**
 * Solo i campi cambiati rispetto alla lettura, nel formato di `PATCH` (array con `null` nelle posizioni invariate).
 *
 * @param base - bozza all'ultima lettura
 * @param draft - bozza dell'utente
 */
export function diffDraft(base: IItemDraft, draft: IItemDraft): ILiveItemChanges {
  const out: ILiveItemChanges = {}
  if (draft.name !== base.name) out.name = draft.name
  if (draft.shortDescription !== base.shortDescription) out.shortDescription = draft.shortDescription
  if (draft.description !== base.description) out.description = draft.description
  if (draft.weight !== base.weight) out.weight = draft.weight
  if (draft.extraFlags !== base.extraFlags) out.extraFlags = draft.extraFlags
  if (draft.timer !== base.timer) out.timer = draft.timer
  if (draft.values.some((v, i) => v !== base.values[i])) out.values = draft.values.map((v, i) => (v !== base.values[i] ? v : null))
  const changed = (a: ILiveItemAffect, b: ILiveItemAffect): boolean => a.location !== b.location || a.modifier !== b.modifier
  if (draft.affects.some((a, i) => changed(a, base.affects[i]!))) {
    out.affects = draft.affects.map((a, i) => (changed(a, base.affects[i]!) ? { location: a.location, modifier: a.modifier } : null))
  }
  return out
}
