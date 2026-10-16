/**
 * Converte il valore di un `q-input` numerico (numero, stringa vuota o `null`) in numero oppure `null`.
 *
 * @param value - valore del campo
 * @returns il numero, o `null` se vuoto/non numerico
 */
export function toNumberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isNaN(n) ? null : n
}
