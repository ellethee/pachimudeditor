import type { ITrigger } from '../types/mobs'

/** Gli eventi dei trigger dei mob (fase 1 del gioco). */
export const TRIGGER_TYPES = ['speech', 'greet', 'give', 'random', 'death'] as const

/**
 * Normalizza il valore di `extra.triggers` (lista di trigger, `[]` se assente o non valido).
 * @param value valore grezzo
 * @returns i trigger con tutti i campi
 */
export function settledTriggers(value: unknown): ITrigger[] {
  if (!Array.isArray(value)) return []
  return (value as ITrigger[]).map((x) => ({ type: x.type, argument: x.argument ?? '', chance: x.chance ?? 100, actions: [...(x.actions ?? [])] }))
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
