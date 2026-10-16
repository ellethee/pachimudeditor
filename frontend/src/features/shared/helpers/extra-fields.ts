import { markRaw } from 'vue'
import type { ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import type { IFieldDef, IFieldRow } from '@ilpachi/pachi-kit/fields'
import EnumFlagsField from '../components/EnumFlagsField.vue'
import FlagsField from '../components/FlagsField.vue'
import JsonField from '../components/JsonField.vue'
import { enumLabel } from './enum-labels'
import type { IExtraFieldDescriptor } from '../types/worlds'

/** Descrizione di una chiave di `extra` (dal backend, o dedotta dalla forma del valore per le chiavi non dichiarate). */
type ExtraDesc = Pick<IExtraFieldDescriptor, 'type'> & Partial<Pick<IExtraFieldDescriptor, 'enum' | 'readOnly' | 'nullable'>>

/** Opzione di enum come restituita da `/api/meta/enums`. */
interface IOption {
  value: number | string
  label: string
}

/** Enum del backend (`GET /api/meta/enums`): chiave -> opzioni. */
export type EnumMap = Record<string, unknown>

/** Funzione di traduzione e controllo di esistenza della chiave (vue-i18n). */
export interface IExtraI18n {
  t: (key: string) => string
  te: (key: string) => boolean
}

/** Parametri di {@link createExtraEditor}. */
export interface IExtraEditorOptions extends IExtraI18n {
  /** Chiavi di `extra` dichiarate dal mondo per la risorsa (`useWorld().extraFieldsOf`). */
  descriptors: IExtraFieldDescriptor[]
  /** Il mondo dichiara il campo `extra` per la risorsa. */
  declared: boolean
  /** Il record non è modificabile (mondo in sola lettura, record corrotto): tutti i campi sono disabilitati. */
  readonly?: boolean
  /** `extra` del record (vuoto in creazione). */
  extra: Record<string, unknown> | undefined
  enums: EnumMap | undefined
  /** Posizione della sezione nel dialog. */
  order: number
}

/** Editor di `extra` pronto per un dialog. */
export interface IExtraEditor {
  /** Sezione da aggiungere al dialog (chiave `extra`). */
  section: ISectionDefinition
  /**
   * Chiavi cambiate rispetto al record, da mettere in `extra` del PUT/POST.
   *
   * @param result - `data.sections.extra` del dialog
   * @returns solo le chiavi modificate, o `undefined` se non è cambiato nulla
   */
  collect: (result: unknown) => Record<string, unknown> | undefined
}

/**
 * Deduce l'editor di una chiave sconosciuta dalla forma del valore.
 *
 * @param value - valore corrente
 */
function infer(value: unknown): ExtraDesc {
  if (typeof value === 'number') return { type: 'number' }
  if (typeof value === 'boolean') return { type: 'boolean' }
  if (typeof value === 'string') return { type: 'text' }
  if (Array.isArray(value) && value.every((item) => typeof item === 'string')) return { type: 'flags' }
  return { type: 'json' }
}

/**
 * Opzioni di un enum del backend.
 *
 * @param enums - mappa degli enum
 * @param name - chiave dell'enum
 */
function optionsOf(enums: EnumMap | undefined, name: string | undefined): IOption[] {
  const list = name ? enums?.[name] : undefined
  return Array.isArray(list) ? (list as IOption[]) : []
}

/**
 * Riga di form di una chiave di `extra`.
 *
 * @param key - chiave
 * @param desc - descrizione dell'editor
 * @param label - etichetta
 * @param enums - enum del backend
 * @param i18n - traduzione
 */
function fieldFor(key: string, desc: ExtraDesc, label: string, enums: EnumMap | undefined, i18n: IExtraI18n): IFieldDef {
  const base: IFieldDef = { field: key, label }
  if (desc.readOnly) Object.assign(base, { disable: true, readonly: true, hint: i18n.t('extra.readOnly') })
  switch (desc.type) {
    case 'number':
      return { ...base, type: 'number' }
    case 'boolean':
      return { ...base, type: 'boolean' }
    case 'enum':
    case 'select': {
      const options = optionsOf(enums, desc.enum ?? undefined)
      const byLabel = desc.type === 'enum'
      if (options.length === 0) return { ...base, ...(byLabel ? {} : { type: 'number' }) }
      return {
        ...base,
        type: 'select',
        options: byLabel ? options.map((option) => ({ label: enumLabel(desc.enum!, option), value: option.label })) : options.map((option) => ({ ...option, label: enumLabel(desc.enum!, option) })),
        clearable: byLabel,
      }
    }
    case 'flags': {
      const options = optionsOf(enums, desc.enum ?? undefined).map((option) => option.label)
      return options.length
        ? { ...base, component: markRaw(EnumFlagsField), options, hint: base.hint ?? i18n.t('extra.flagsHint') }
        : { ...base, component: markRaw(FlagsField) }
    }
    case 'json':
      return { ...base, component: markRaw(JsonField), hint: i18n.t('extra.jsonHint') }
    default:
      return { ...base, ...(desc.nullable ? { clearable: true } : {}) }
  }
}

/**
 * Crea l'editor dei campi `extra` di un'entità, oppure `null` se non serve (il mondo non dichiara `extra` e
 * il record non ne ha: pachimud resta com'era).
 *
 * Ogni chiave dichiarata dal backend è un campo (tipo, enum, sola lettura, etichetta); le chiavi di
 * diagnostica (`group: diagnostic`) non sono campi: le mostra il banner del record. Le chiavi del record non
 * dichiarate si deducono dalla forma del valore. Le chiavi sola lettura sono disabilitate e mai inviate; le
 * altre solo se cambiate.
 *
 * @param options - vedi {@link IExtraEditorOptions}
 */
export function createExtraEditor(options: IExtraEditorOptions): IExtraEditor | null {
  const extra = options.extra ?? {}
  const known = new Map(options.descriptors.map((desc) => [desc.name, desc]))
  const keys = [...new Set([...known.keys(), ...Object.keys(extra)])].filter((key) => known.get(key)?.group !== 'diagnostic')
  if (!options.declared && keys.length === 0) return null
  const descriptors = new Map<string, ExtraDesc>(keys.map((key) => [key, known.get(key) ?? infer(extra[key])]))
  const rows: IFieldRow[] = keys.map((key) => {
    const labelKey = known.get(key)?.labelKey ?? `extra.labels.${key}`
    const label = options.te(labelKey) ? options.t(labelKey) : key
    const desc = descriptors.get(key)!
    const locked = options.readonly ? { ...desc, readOnly: true } : desc
    return [fieldFor(key, locked, label, options.enums, options)]
  })
  return {
    section: {
      key: 'extra',
      title: options.t('extra.title'),
      component: markRaw(FieldsSection),
      props: { rows },
      initialValue: extra,
      order: options.order,
      container: { type: 'expansion', title: options.t('extra.title'), defaultOpened: false },
    },
    collect(result) {
      if (!result || typeof result !== 'object') return undefined
      const changed: Record<string, unknown> = {}
      for (const [key, raw] of Object.entries(result as Record<string, unknown>)) {
        const desc = descriptors.get(key)
        if (!desc || desc.readOnly) continue
        const value = desc.nullable && raw === '' ? null : raw
        const before = extra[key]
        const emptyNew = before === undefined && (value === undefined || value === '' || (Array.isArray(value) && value.length === 0))
        if (!emptyNew && value !== undefined && JSON.stringify(before) !== JSON.stringify(value)) changed[key] = value
      }
      return Object.keys(changed).length ? changed : undefined
    },
  }
}
