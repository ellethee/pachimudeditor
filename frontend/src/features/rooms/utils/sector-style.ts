/**
 * Colore di un tipo di terreno, per bordo e fascia dei nodi della mappa. Indicizzato per
 * valore numerico (stesso ordine di `SectorType` del backend), non per nome, così non dipende
 * dalle label restituite da `/api/meta/enums`.
 */
export const SECTOR_COLOR: Record<number, string> = {
  0: '#8d6e63', // INSIDE
  1: '#78909c', // CITY
  2: '#9ccc65', // FIELD
  3: '#2e7d32', // FOREST
  4: '#a1887f', // HILLS
  5: '#6d4c41', // MOUNTAIN
  6: '#42a5f5', // WATER_SWIM
  7: '#1565c0', // WATER_NOSWIM
  8: '#b39ddb', // FLYING
  9: '#00838f', // UNDERWATER
}

const FALLBACK_COLOR = '#9e9e9e'

/**
 * Colore associato a un tipo di terreno.
 *
 * @param sectorType - valore numerico del terreno
 * @returns colore CSS (grigio se sconosciuto)
 */
export function sectorColor(sectorType: number): string {
  return SECTOR_COLOR[sectorType] ?? FALLBACK_COLOR
}
