import type { IFilterSpec } from '../../shared/helpers/list-filters'

/** Campi numerici con filtro a intervallo (`min<Campo>`/`max<Campo>` nel backend). */
export const RANGE_KEYS = [
  'level',
  'thac0',
  'armorClass',
  'hpDiceCount',
  'hpDieSize',
  'hpBonus',
  'damageDiceCount',
  'damageDieSize',
  'damageBonus',
  'gold',
  'experience',
  'alignment',
] as const

/** Filtri della lista mob nell'ordine di visualizzazione (chiave di stato = parametro di query). */
export const FILTER_SPECS: IFilterSpec[] = [
  { key: 'sex', param: 'sex', kind: 'list', numeric: true },
  { key: 'flags', param: 'flag', kind: 'list' },
  { key: 'raceId', param: 'raceId', kind: 'list' },
  { key: 'classId', param: 'classId', kind: 'list' },
  ...RANGE_KEYS.map((key): IFilterSpec => ({ key, param: key, kind: 'range' })),
]

/** Nomi delle colonne selezionabili, nell'ordine di visualizzazione (sono anche le chiavi di `orderBy` del backend). */
export const COLUMN_NAMES = [
  'vnum',
  'shortDescription',
  'zoneId',
  'level',
  'sex',
  'raceId',
  'classId',
  'alignment',
  'armorClass',
  'thac0',
  'hpDiceCount',
  'hpDieSize',
  'hpBonus',
  'damageDiceCount',
  'damageDieSize',
  'damageBonus',
  'gold',
  'experience',
  'flags',
] as const

/** Colonne di default: poche su telefono, le principali altrimenti. */
export function defaultColumns(compact: boolean): string[] {
  return compact
    ? ['vnum', 'shortDescription', 'level', 'armorClass']
    : ['vnum', 'shortDescription', 'zoneId', 'level', 'sex', 'raceId', 'classId', 'armorClass', 'gold']
}

/** Chiave del localStorage con le colonne scelte (comodità per-viewer, mai stato affidabile). */
export const COLUMNS_KEY = 'pachimudeditor.mobs.columns'
