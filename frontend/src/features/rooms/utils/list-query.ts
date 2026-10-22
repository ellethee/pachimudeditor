import type { IFilterSpec } from '../../shared/helpers/list-filters'

/** Campi numerici con filtro a intervallo (`min<Campo>`/`max<Campo>` nel backend). */
export const RANGE_KEYS = ['healRate', 'manaRate'] as const

/** Filtri della lista stanze nell'ordine di visualizzazione (chiave di stato = parametro di query, tranne `flags` -> `flag`). */
export const FILTER_SPECS: IFilterSpec[] = [
  { key: 'sectorType', param: 'sectorType', kind: 'list', numeric: true },
  { key: 'flags', param: 'flag', kind: 'list' },
  { key: 'clanId', param: 'clanId', kind: 'list' },
  { key: 'owner', param: 'owner', kind: 'text' },
  ...RANGE_KEYS.map((key): IFilterSpec => ({ key, param: key, kind: 'range' })),
]

/** Nomi delle colonne selezionabili, nell'ordine di visualizzazione (sono anche le chiavi di `orderBy` del backend). */
export const COLUMN_NAMES = ['vnum', 'name', 'zoneId', 'sectorType', 'flags', 'healRate', 'manaRate', 'clanId', 'owner'] as const

/** Colonne di default: poche su telefono, le principali altrimenti. */
export function defaultColumns(compact: boolean): string[] {
  return compact ? ['vnum', 'name', 'sectorType'] : ['vnum', 'name', 'zoneId', 'sectorType', 'flags', 'healRate', 'manaRate']
}

/** Chiave del localStorage con le colonne scelte (comodità per-viewer, mai stato affidabile). */
export const COLUMNS_KEY = 'pachimudeditor.rooms.columns'
