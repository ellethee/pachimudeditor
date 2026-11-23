import type { ILocated } from '../types/content-files'

/**
 * La pagina dell'editor che mostra la voce di un problema.
 * @param target risultato di `locateIssues`
 * @returns il percorso (stanza, mob, oggetto, reset o zona), `null` se il file non è dell'editor
 */
export function issueRoute(target: ILocated | null): string | null {
  if (!target || target.kind === 'none') return null
  if (target.kind === 'room' && target.vnum !== null) return `/rooms/${target.vnum}`
  if (target.kind === 'mob' && target.vnum !== null) return `/mobs/${target.vnum}`
  if (target.kind === 'object' && target.vnum !== null) return `/objects/${target.vnum}`
  if (target.zoneId === null) return null
  return target.kind === 'resets' ? `/zones/${target.zoneId}/resets` : `/zones/${target.zoneId}`
}
