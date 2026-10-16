/**
 * Costanti della bussola condivise dal grafo delle stanze. `Direction` usa gli stessi
 * interi del backend: NORTH=0 EAST=1 SOUTH=2 WEST=3 UP=4 DOWN=5.
 */

export const DIRECTIONS = [0, 1, 2, 3, 4, 5] as const
export type DirectionValue = (typeof DIRECTIONS)[number]

/** Direzione opposta (per gli attacchi degli archi bidirezionali). */
export const OPPOSITE: Record<DirectionValue, DirectionValue> = {
  0: 2,
  2: 0,
  1: 3,
  3: 1,
  4: 5,
  5: 4,
}
