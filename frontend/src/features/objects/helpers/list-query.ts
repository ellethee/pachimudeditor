import type { LocationQuery } from 'vue-router'

/** Campi numerici con filtro a intervallo (`min<Campo>`/`max<Campo>` nel backend). */
export const RANGE_KEYS = ['weight', 'cost', 'rent', 'value0', 'value1', 'value2', 'value3'] as const
/** Nome di un campo con intervallo. */
export type RangeKey = (typeof RANGE_KEYS)[number]

/** Intervallo inclusivo; un estremo assente non limita. */
export interface IRange {
  min?: number | undefined
  max?: number | undefined
}

/** Filtri della lista oggetti (oltre alla zona e alla ricerca testuale, gestite a parte). */
export interface IObjectFilters {
  /** Tipi oggetto (OR). */
  types: number[]
  /** Flag di indossabilità richiesti (AND). */
  wear: string[]
  /** Flag extra richiesti (AND). */
  extra: string[]
  /** Apply presente tra gli affect (vuoto: nessun filtro). */
  affect: string
  /** Valore minimo dell'affect (richiede `affect`). */
  minAffect?: number | undefined
  ranges: Record<RangeKey, IRange>
}

/** Filtri vuoti (lista senza restrizioni). */
export function emptyFilters(): IObjectFilters {
  return {
    types: [],
    wear: [],
    extra: [],
    affect: '',
    ranges: Object.fromEntries(RANGE_KEYS.map((key) => [key, {}])) as Record<RangeKey, IRange>,
  }
}

/**
 * `true` se l'intervallo ha il minimo maggiore del massimo (il backend risponderebbe 422).
 *
 * @param range - intervallo da controllare
 */
export function rangeInvalid(range: IRange): boolean {
  return range.min !== undefined && range.max !== undefined && range.min > range.max
}

const cap = (key: string): string => key.charAt(0).toUpperCase() + key.slice(1)

/**
 * Parametri di query (nomi del backend) dei filtri attivi. Gli elenchi sono separati da virgole.
 *
 * @param filters - filtri
 * @param keepInvalid - mantiene anche gli intervalli incoerenti (per l'URL); per la richiesta si scartano
 */
export function filtersToParams(filters: IObjectFilters, keepInvalid = false): Record<string, string | number> {
  const params: Record<string, string | number> = {}
  if (filters.types.length) params.objectType = filters.types.join(',')
  if (filters.wear.length) params.wearFlag = filters.wear.join(',')
  if (filters.extra.length) params.extraFlag = filters.extra.join(',')
  if (filters.affect) {
    params.affect = filters.affect
    if (filters.minAffect !== undefined) params.minAffect = filters.minAffect
  }
  for (const key of RANGE_KEYS) {
    const range = filters.ranges[key]
    if (!keepInvalid && rangeInvalid(range)) continue
    if (range.min !== undefined) params[`min${cap(key)}`] = range.min
    if (range.max !== undefined) params[`max${cap(key)}`] = range.max
  }
  return params
}

/** Primo valore di un parametro di query. */
function first(value: LocationQuery[string] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? ''
}

/** Numero intero da una stringa di query (`undefined` se vuota o non numerica). */
function int(value: LocationQuery[string] | undefined): number | undefined {
  const text = first(value).trim()
  return /^-?\d+$/.test(text) ? Number(text) : undefined
}

/** Elenco da una stringa separata da virgole. */
function list(value: LocationQuery[string] | undefined): string[] {
  return first(value)
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

/**
 * Filtri ricostruiti dalla query string dell'URL (valori non validi ignorati).
 *
 * @param query - `route.query`
 */
export function filtersFromQuery(query: LocationQuery): IObjectFilters {
  const filters = emptyFilters()
  filters.types = list(query.objectType)
    .map(Number)
    .filter((value) => Number.isInteger(value))
  filters.wear = list(query.wearFlag)
  filters.extra = list(query.extraFlag)
  filters.affect = first(query.affect).trim()
  filters.minAffect = filters.affect ? int(query.minAffect) : undefined
  for (const key of RANGE_KEYS) filters.ranges[key] = { min: int(query[`min${cap(key)}`]), max: int(query[`max${cap(key)}`]) }
  return filters
}

/** Nomi dei parametri di query posseduti dai filtri (da togliere dall'URL prima di riscriverli). */
export const FILTER_QUERY_KEYS: string[] = [
  'objectType',
  'wearFlag',
  'extraFlag',
  'affect',
  'minAffect',
  ...RANGE_KEYS.flatMap((key) => [`min${cap(key)}`, `max${cap(key)}`]),
]

/**
 * Numero di filtri attivi (ogni elenco o intervallo conta uno).
 *
 * @param filters - filtri
 */
export function activeCount(filters: IObjectFilters): number {
  return (
    Number(filters.types.length > 0) +
    Number(filters.wear.length > 0) +
    Number(filters.extra.length > 0) +
    Number(filters.affect !== '') +
    RANGE_KEYS.filter((key) => filters.ranges[key].min !== undefined || filters.ranges[key].max !== undefined).length
  )
}

/** Nomi delle colonne selezionabili, nell'ordine di visualizzazione. */
export const COLUMN_NAMES = [
  'vnum',
  'shortDescription',
  'zoneId',
  'objectType',
  'weight',
  'cost',
  'rent',
  'value0',
  'value1',
  'value2',
  'value3',
  'wearFlags',
  'affects',
] as const

/** Colonne di default: poche su telefono, le principali altrimenti. */
export function defaultColumns(compact: boolean): string[] {
  return compact
    ? ['vnum', 'shortDescription', 'objectType', 'cost']
    : ['vnum', 'shortDescription', 'zoneId', 'objectType', 'weight', 'cost', 'rent', 'wearFlags']
}

/** Chiave del localStorage con le colonne scelte (comodità per-viewer, mai stato affidabile). */
const COLUMNS_KEY = 'pachimudeditor.objects.columns'

/**
 * Colonne salvate dal viewer (`null` se assenti, non valide o localStorage non disponibile).
 */
export function loadColumns(): string[] | null {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(COLUMNS_KEY) ?? 'null')
    if (!Array.isArray(parsed)) return null
    const known = parsed.filter((name): name is string => (COLUMN_NAMES as readonly string[]).includes(name as string))
    return known.length ? known : null
  } catch {
    return null
  }
}

/**
 * Salva le colonne scelte (errori di storage ignorati).
 *
 * @param names - nomi delle colonne visibili
 */
export function saveColumns(names: string[]): void {
  try {
    window.localStorage.setItem(COLUMNS_KEY, JSON.stringify(names))
  } catch {
    // storage non disponibile: la scelta vale solo per la sessione
  }
}

/**
 * Riepilogo testuale di un elenco (primi elementi e «+n»).
 *
 * @param items - elementi
 * @param max - numero massimo di elementi mostrati
 */
export function summarize(items: string[], max = 3): string {
  if (items.length <= max) return items.join(', ')
  return `${items.slice(0, max).join(', ')} +${items.length - max}`
}

/**
 * Riepilogo degli affect (`apply +n`).
 *
 * @param affects - dizionario apply -> valore
 */
export function summarizeAffects(affects: Record<string, number>): string {
  return summarize(Object.entries(affects).map(([name, value]) => `${name} ${value > 0 ? '+' : ''}${value}`), 2)
}
