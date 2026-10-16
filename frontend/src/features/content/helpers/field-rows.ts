import { markRaw } from 'vue'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import ContentFlagsField from '../components/ContentFlagsField.vue'
import StatHeading from '../components/StatHeading.vue'
import type { IClass, IContentOptions, IRace, IStats } from '../types/content'

/** Funzione di traduzione (`t` di vue-i18n). */
export type Translate = (key: string, params?: Record<string, unknown>) => string

/** Stile dei campi affiancati: dividono la riga in parti uguali. */
const SIDE_BY_SIDE = 'flex: 1 1 0; min-width: 130px'

/** Le sei caratteristiche, nell'ordine in cui sono mostrate. */
export const STAT_KEYS: (keyof IStats)[] = ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma']

/** Regola: id ammesso (minuscole, cifre, underscore). */
function idRule(message: string) {
  return (value: unknown) => /^[a-z0-9][a-z0-9_]{0,63}$/.test(String(value ?? '')) || message
}

/** Opzioni `{ value, label }` da un elenco di stringhe. */
function toOptions(values: string[]): { value: string; label: string }[] {
  return values.map((value) => ({ value, label: value }))
}

/**
 * Righe della sezione generale del form razza.
 * @param t traduzione
 * @param options valori ammessi (taglie)
 * @param editing `true` in modifica (l'id non è modificabile)
 */
export function buildRaceGeneralRows(t: Translate, options: IContentOptions, editing: boolean): IFieldRow[] {
  return [
    [
      { field: 'raceId', label: t('content.races.fields.raceId'), required: true, disable: editing, rules: [idRule(t('content.validation.id'))], style: SIDE_BY_SIDE },
      { field: 'name', label: t('content.races.fields.name'), required: true, style: SIDE_BY_SIDE },
      { field: 'whoName', label: t('content.races.fields.whoName'), hint: t('content.races.fields.whoNameHint'), style: SIDE_BY_SIDE },
    ],
    [{ field: 'description', label: t('content.races.fields.description'), type: 'textarea', autogrow: true, required: true }],
    [
      { field: 'size', label: t('content.races.fields.size'), type: 'select', options: toOptions(options.sizes), style: SIDE_BY_SIDE },
      { field: 'points', label: t('content.races.fields.points'), type: 'number', style: SIDE_BY_SIDE },
      { field: 'extraTrainingCap', label: t('content.races.fields.extraTrainingCap'), type: 'number', style: SIDE_BY_SIDE },
      { field: 'startRoom', label: t('content.races.fields.startRoom'), type: 'number', hint: t('content.races.fields.startRoomHint'), style: SIDE_BY_SIDE },
    ],
    [{ field: 'mobOnly', label: t('content.races.fields.mobOnly'), type: 'boolean' }],
  ]
}

/**
 * Righe della sezione flag del form razza.
 * @param t traduzione
 * @param options valori ammessi
 */
export function buildRaceFlagRows(t: Translate, options: IContentOptions): IFieldRow[] {
  const flags = (field: string, choices: string[]): IFieldRow => [
    { field, label: t(`content.races.fields.${field}`), component: markRaw(ContentFlagsField), choices },
  ]
  return [
    flags('mobFlags', options.mobFlags),
    flags('offensiveFlags', options.offensiveFlags),
    flags('affectedBy', options.affectedByFlags),
    flags('immunity', options.resistanceFlags),
    flags('resistance', options.resistanceFlags),
    flags('vulnerability', options.resistanceFlags),
    flags('form', options.formFlags),
    flags('parts', options.partFlags),
    [{ field: 'skills', label: t('content.races.fields.skills'), type: 'select', multiple: true, useChips: true, useInput: true, newValueMode: 'add-unique', hideDropdownIcon: true, hint: t('content.races.fields.skillsHint') }],
  ]
}

/**
 * Righe della sezione caratteristiche del form razza: `stats_*` (iniziali) e `maxStats_*` (massime).
 * @param t traduzione
 */
export function buildRaceStatRows(t: Translate): IFieldRow[] {
  const row = (prefix: 'stats' | 'maxStats'): IFieldRow =>
    STAT_KEYS.map((key) => ({
      field: `${prefix}_${key}`,
      label: `${t(`content.stats.${key}`)}`,
      type: 'number',
      style: SIDE_BY_SIDE,
    }))
  return [
    [{ field: '_h1', label: '', component: markRaw(StatHeading), text: t('content.races.fields.stats') }],
    row('stats'),
    [{ field: '_h2', label: '', component: markRaw(StatHeading), text: t('content.races.fields.maxStats') }],
    row('maxStats'),
  ]
}

/**
 * Righe della sezione generale del form classe.
 * @param t traduzione
 * @param options valori ammessi (caratteristiche)
 * @param editing `true` in modifica (l'id non è modificabile)
 */
export function buildClassGeneralRows(t: Translate, options: IContentOptions, editing: boolean): IFieldRow[] {
  return [
    [
      { field: 'classId', label: t('content.classes.fields.classId'), required: true, disable: editing, rules: [idRule(t('content.validation.id'))], style: SIDE_BY_SIDE },
      { field: 'name', label: t('content.classes.fields.name'), required: true, style: SIDE_BY_SIDE },
      { field: 'abbreviation', label: t('content.classes.fields.abbreviation'), style: SIDE_BY_SIDE },
    ],
    [{ field: 'description', label: t('content.classes.fields.description'), type: 'textarea', autogrow: true }],
    [
      { field: 'attrPrime', label: t('content.classes.fields.attrPrime'), type: 'select', options: options.stats.map((value) => ({ value, label: t(`content.stats.${value}`) })), clearable: true, style: SIDE_BY_SIDE },
      { field: 'addStrength', label: t('content.classes.fields.addStrength'), type: 'boolean', style: SIDE_BY_SIDE },
    ],
    [{ field: 'attrsPriority', label: t('content.classes.fields.attrsPriority'), component: markRaw(ContentFlagsField), choices: options.stats, hint: t('content.classes.fields.attrsPriorityHint') }],
  ]
}

/**
 * Righe della sezione combattimento del form classe.
 * @param t traduzione
 */
export function buildClassCombatRows(t: Translate): IFieldRow[] {
  const num = (field: string): IFieldRow[number] => ({ field, label: t(`content.classes.fields.${field}`), type: 'number', style: SIDE_BY_SIDE })
  return [
    [num('thac000'), num('thac032')],
    [num('hpMin'), num('hpMax')],
    [num('weapon'), num('skillAdept')],
  ]
}

/**
 * Stato iniziale del form razza: appiattisce `stats`/`maxStats` in `stats_*`/`maxStats_*` e porta a `[]` le liste assenti.
 * @param race razza da modificare, o valori di default per una nuova
 */
export function raceToForm(race: Partial<IRace>): Record<string, unknown> {
  const form: Record<string, unknown> = { ...race }
  for (const key of ['mobFlags', 'offensiveFlags', 'affectedBy', 'immunity', 'resistance', 'vulnerability', 'form', 'parts', 'skills'] as const) {
    form[key] = [...(race[key] ?? [])]
  }
  for (const key of STAT_KEYS) {
    form[`stats_${key}`] = race.stats?.[key] ?? 0
    form[`maxStats_${key}`] = race.maxStats?.[key] ?? 0
  }
  return form
}

/**
 * Corpo della richiesta dal form razza: ricompone `stats`/`maxStats` ed elimina i campi di sola UI.
 * @param form stato unito delle sezioni
 */
export function formToRace(form: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  const stats: Record<string, unknown> = {}
  const maxStats: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(form)) {
    if (key.startsWith('_') || key === 'file' || key === 'disabled' || key === 'mobCount' || key === 'valid' || key === 'error') continue
    if (key.startsWith('stats_')) stats[key.slice(6)] = Number(value ?? 0)
    else if (key.startsWith('maxStats_')) maxStats[key.slice(9)] = Number(value ?? 0)
    else if (key !== 'stats' && key !== 'maxStats') body[key] = value === '' ? null : value
  }
  // un blocco assente nel file e lasciato a zero non viene creato (nessun rumore nello YAML)
  if (form.stats || Object.values(stats).some(Boolean)) body.stats = stats
  if (form.maxStats || Object.values(maxStats).some(Boolean)) body.maxStats = maxStats
  return body
}

/**
 * Corpo della richiesta dal form classe (toglie i metadati di sola lettura).
 * @param form stato unito delle sezioni
 */
export function formToClass(form: Record<string, unknown> & Partial<IClass>): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(form)) {
    if (key === 'file' || key === 'disabled' || key === 'mobCount' || key === 'valid' || key === 'error') continue
    body[key] = value === '' && key === 'attrPrime' ? '' : value
  }
  return body
}
