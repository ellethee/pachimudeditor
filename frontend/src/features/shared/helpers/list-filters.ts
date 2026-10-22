import type { LocationQuery } from 'vue-router'

/** Intervallo inclusivo; un estremo assente non limita. */
export interface IRange {
  min?: number | undefined
  max?: number | undefined
}

/** Tipo di filtro: elenco di valori (multi-selezione), testo libero o intervallo numerico. */
export type FilterKind = 'list' | 'text' | 'range'

/** Definizione di un filtro: chiave nello stato e nome del parametro di query (`min<Param>`/`max<Param>` per gli intervalli). */
export interface IFilterSpec {
  key: string
  param: string
  kind: FilterKind
  /** `true` se i valori dell'elenco sono numeri (enum del backend). */
  numeric?: boolean
}

/** Opzione di un filtro a elenco. */
export interface IFilterOption {
  value: string | number
  label: string
}

/** Controllo di un filtro: la definizione (`IFilterSpec`) più testi e opzioni. */
export interface IFilterControl extends IFilterSpec {
  /** Etichetta (già tradotta). */
  label: string
  /** Etichetta breve per gli estremi di un intervallo («Livello min»); default: `label`. */
  short?: string | undefined
  /** Opzioni note dell'elenco (vuoto con `free`: inserimento libero). */
  options?: IFilterOption[] | undefined
  /** `true` se si possono digitare valori non presenti nelle opzioni (flag, clan). */
  free?: boolean | undefined
  /** `true` se il mondo non ha il campo: il filtro non si mostra. */
  hidden?: boolean | undefined
}

/** Stato dei filtri di una lista (oltre alla zona e alla ricerca testuale, gestite a parte). */
export interface IListFilters {
  lists: Record<string, (string | number)[]>
  texts: Record<string, string>
  ranges: Record<string, IRange>
}

/** Filtri vuoti (lista senza restrizioni). */
export function emptyFilters(specs: IFilterSpec[]): IListFilters {
  const filters: IListFilters = { lists: {}, texts: {}, ranges: {} }
  for (const spec of specs) {
    if (spec.kind === 'list') filters.lists[spec.key] = []
    else if (spec.kind === 'text') filters.texts[spec.key] = ''
    else filters.ranges[spec.key] = {}
  }
  return filters
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
 * @param specs - definizione dei filtri
 * @param filters - filtri
 * @param keepInvalid - mantiene anche gli intervalli incoerenti (per l'URL); per la richiesta si scartano
 */
export function filtersToParams(specs: IFilterSpec[], filters: IListFilters, keepInvalid = false): Record<string, string | number> {
  const params: Record<string, string | number> = {}
  for (const spec of specs) {
    if (spec.kind === 'list') {
      const values = filters.lists[spec.key] ?? []
      if (values.length) params[spec.param] = values.join(',')
    } else if (spec.kind === 'text') {
      const text = (filters.texts[spec.key] ?? '').trim()
      if (text) params[spec.param] = text
    } else {
      const range = filters.ranges[spec.key] ?? {}
      if (!keepInvalid && rangeInvalid(range)) continue
      if (range.min !== undefined) params[`min${cap(spec.param)}`] = range.min
      if (range.max !== undefined) params[`max${cap(spec.param)}`] = range.max
    }
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
 * @param specs - definizione dei filtri
 * @param query - `route.query`
 */
export function filtersFromQuery(specs: IFilterSpec[], query: LocationQuery): IListFilters {
  const filters = emptyFilters(specs)
  for (const spec of specs) {
    if (spec.kind === 'list') {
      const values = list(query[spec.param])
      filters.lists[spec.key] = spec.numeric ? values.map(Number).filter((value) => Number.isInteger(value)) : values
    } else if (spec.kind === 'text') {
      filters.texts[spec.key] = first(query[spec.param]).trim()
    } else {
      filters.ranges[spec.key] = { min: int(query[`min${cap(spec.param)}`]), max: int(query[`max${cap(spec.param)}`]) }
    }
  }
  return filters
}

/**
 * Nomi dei parametri di query posseduti dai filtri (da togliere dall'URL prima di riscriverli).
 *
 * @param specs - definizione dei filtri
 */
export function filterQueryKeys(specs: IFilterSpec[]): string[] {
  return specs.flatMap((spec) => (spec.kind === 'range' ? [`min${cap(spec.param)}`, `max${cap(spec.param)}`] : [spec.param]))
}

/**
 * Numero di filtri attivi (ogni elenco, testo o intervallo conta uno).
 *
 * @param specs - definizione dei filtri
 * @param filters - filtri
 */
export function activeCount(specs: IFilterSpec[], filters: IListFilters): number {
  return specs.filter((spec) => {
    if (spec.kind === 'list') return (filters.lists[spec.key] ?? []).length > 0
    if (spec.kind === 'text') return (filters.texts[spec.key] ?? '').trim() !== ''
    const range = filters.ranges[spec.key]
    return range !== undefined && (range.min !== undefined || range.max !== undefined)
  }).length
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
 * Colonne salvate dal viewer (`null` se assenti, non valide o localStorage non disponibile).
 *
 * @param storageKey - chiave del localStorage
 * @param allowed - nomi di colonna ammessi (quelli sconosciuti si scartano)
 */
export function loadColumns(storageKey: string, allowed: readonly string[]): string[] | null {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(storageKey) ?? 'null')
    if (!Array.isArray(parsed)) return null
    const known = parsed.filter((name): name is string => allowed.includes(name as string))
    return known.length ? known : null
  } catch {
    return null
  }
}

/**
 * Salva le colonne scelte (errori di storage ignorati: comodità per-viewer, mai stato affidabile).
 *
 * @param storageKey - chiave del localStorage
 * @param names - nomi delle colonne visibili
 */
export function saveColumns(storageKey: string, names: string[]): void {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(names))
  } catch {
    // storage non disponibile: la scelta vale solo per la sessione
  }
}
