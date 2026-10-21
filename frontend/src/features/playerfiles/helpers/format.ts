import type { PlayerColumnType } from '../types/player-files'

/**
 * Durata in secondi come «12h 03m» (o «45s» sotto il minuto).
 *
 * @param seconds - secondi
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`
}

/**
 * Valore di una colonna come testo (`—` se nullo).
 *
 * @param value - valore grezzo del backend
 * @param type - tipo dichiarato dalla colonna
 * @param locale - locale per le date
 * @param yes - testo per `true`
 * @param no - testo per `false`
 */
export function formatCell(value: unknown, type: PlayerColumnType, locale: string, yes: string, no: string): string {
  if (value === null || value === undefined || value === '') return '—'
  if (type === 'boolean') return value ? yes : no
  if (type === 'duration' && typeof value === 'number') return formatDuration(value)
  if (type === 'datetime' && typeof value === 'string') {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString(locale)
  }
  if (type === 'number' && typeof value === 'number') return value.toLocaleString(locale)
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
