import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import type { IEnumOption } from '../types/zones'

/** Funzione di traduzione (sottoinsieme di `t` di vue-i18n). */
type TTranslate = (key: string) => string

/** Funzione di traduzione con parametri. */
type TFormat = (key: string, params?: Record<string, unknown>) => string

/**
 * Regola numerica: accetta `null` (campo vuoto, gestito da `required`) o un intero >= `min`.
 * @param min valore minimo ammesso
 * @param message messaggio d'errore
 */
function minRule(min: number, message: string) {
  return (value: unknown) => value === null || Number(value) >= min || message
}

/**
 * Righe di campi del form di creazione/modifica zona.
 * @param t funzione di traduzione
 * @param resetModes opzioni di `zoneResetMode`
 * @param editing true in modifica (il vnum non è modificabile)
 */
export function buildZoneFieldRows(
  t: TTranslate,
  resetModes: IEnumOption[],
  editing: boolean,
): { general: IFieldRow[]; ranges: IFieldRow[] } {
  const nonNegative = minRule(0, t('zones.validation.nonNegative'))
  const minOne = minRule(1, t('zones.validation.minOne'))
  return {
    general: [
      [
        { field: 'vnum', label: t('zones.form.vnum'), type: 'number', required: true, disable: editing, rules: editing ? [] : [nonNegative] },
        { field: 'name', label: t('zones.form.name'), required: true },
      ],
      [{ field: 'builder', label: t('zones.form.builder') }],
      [{ field: 'enabled', label: t('zones.form.enabled'), type: 'boolean' }],
    ],
    ranges: [
      [
        { field: 'bottomVnum', label: t('zones.form.bottomVnum'), type: 'number', required: true, rules: [nonNegative] },
        { field: 'topVnum', label: t('zones.form.topVnum'), type: 'number', required: true, rules: [nonNegative] },
      ],
      [
        { field: 'minLevel', label: t('zones.form.minLevel'), type: 'number', required: true, rules: [minOne] },
        { field: 'maxLevel', label: t('zones.form.maxLevel'), type: 'number', required: true, rules: [minOne] },
      ],
      [
        { field: 'lifespanMinutes', label: t('zones.form.lifespanMinutes'), type: 'number', required: true, rules: [nonNegative] },
        { field: 'resetMode', label: t('zones.form.resetMode'), type: 'select', options: resetModes, required: true },
      ],
    ],
  }
}

/**
 * Righe di campi del dialogo di clonazione.
 * @param t funzione di traduzione
 * @param suggestedVnum primo vnum libero, mostrato come suggerimento (non precompilato: il dialogo permette
 * di salvare solo dopo una modifica)
 */
export function buildCloneFieldRows(t: TFormat, suggestedVnum: number | null): IFieldRow[] {
  return [
    [
      {
        field: 'vnum',
        label: t('zones.clone.vnum'),
        type: 'number',
        required: true,
        rules: [minRule(0, t('zones.validation.nonNegative'))],
        ...(suggestedVnum === null ? {} : { hint: t('zones.clone.vnumHint', { vnum: suggestedVnum }) }),
      },
    ],
    [{ field: 'name', label: t('zones.clone.name'), required: true }],
    [{ field: 'copyResetCommands', label: t('zones.clone.copyResetCommands'), type: 'boolean' }],
  ]
}
