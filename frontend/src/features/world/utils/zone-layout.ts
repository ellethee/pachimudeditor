/** Posizione di un nodo. */
export interface IPoint {
  x: number
  y: number
}

/**
 * Dispone `count` nodi su una circonferenza (raggio proporzionale al numero di nodi, così non si
 * sovrappongono). Con un solo nodo lo mette nell'origine.
 *
 * @param count - numero di nodi
 * @param spacing - distanza minima tra nodi adiacenti, in pixel
 */
export function circleLayout(count: number, spacing = 220): IPoint[] {
  if (count <= 1) return count === 1 ? [{ x: 0, y: 0 }] : []
  const radius = Math.max(spacing, (count * spacing) / (2 * Math.PI))
  return Array.from({ length: count }, (_, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2
    return { x: Math.round(radius * Math.cos(angle)), y: Math.round(radius * Math.sin(angle)) }
  })
}
