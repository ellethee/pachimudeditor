import { currentWorldHeader } from '../../shared/helpers/world-state'

/** Posizioni trascinate a mano: id nodo -> coordinate in pixel. */
export type LayoutOverrides = Record<string, { x: number; y: number }>

/** Chiave di localStorage del layout di una zona (per mondo: gli id di mondi diversi possono coincidere). */
function storageKey(zoneId: number): string {
  return `pachimudeditor.rooms.layout.${currentWorldHeader() ?? 'default'}.${zoneId}`
}

/**
 * Posizioni salvate di una zona.
 *
 * @param zoneId - id della zona
 * @returns le posizioni (vuote se assenti o se localStorage non è disponibile)
 */
export function loadLayout(zoneId: number): LayoutOverrides {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(storageKey(zoneId)) ?? '{}')
    return parsed !== null && typeof parsed === 'object' ? (parsed as LayoutOverrides) : {}
  } catch {
    return {}
  }
}

/**
 * Salva le posizioni di una zona.
 *
 * @param zoneId - id della zona
 * @param layout - posizioni da ricordare
 */
export function saveLayout(zoneId: number, layout: LayoutOverrides): void {
  try {
    window.localStorage.setItem(storageKey(zoneId), JSON.stringify(layout))
  } catch {
    // localStorage non disponibile: il layout vale solo per questa sessione
  }
}

/** Dimentica le posizioni di una zona (si torna al layout del server). */
export function clearLayout(zoneId: number): void {
  try {
    window.localStorage.removeItem(storageKey(zoneId))
  } catch {
    // niente da fare
  }
}
