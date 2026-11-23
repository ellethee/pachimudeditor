import { markRaw } from 'vue'
import type { IFieldDef, IFieldRow } from '@ilpachi/pachi-kit/fields'
import EnumFlagsField from '../components/EnumFlagsField.vue'
import FlagsField from '../components/FlagsField.vue'
import type { IFieldDescriptor } from '../types/worlds'

/** Spiegazione di un flag del catalogo del mondo (`Option` di `GET /api/meta/enums`, campi facoltativi). */
export interface IFlagDetail {
  /** Testo per lingua (`it`, `en`). */
  description?: Record<string, string> | null
  /** Altri nomi accettati dal gioco. */
  aliases?: string[] | null
  /** `leu`, `clessidra` o `pachimud`. */
  origin?: string | null
  /** `false`: il gioco accetta il flag ma non lo usa. */
  implemented?: boolean | null
}

/** Opzione di una lista di flag come arriva dal backend. */
interface IFlagOption extends IFlagDetail {
  label: string
}

/** Nomi dei flag ammessi; `details` (se il mondo ha un catalogo) spiega ciascuno. Resta un `string[]` per chi usa solo i nomi. */
export type FlagNames = string[] & { details?: Record<string, IFlagDetail> }

/** Cerca il descrittore di un campo di una risorsa (`useWorld().fieldOf`). */
export type FieldLookup = (resource: string, name: string) => IFieldDescriptor | undefined

/**
 * Applica ai campi di un form i descrittori del mondo (`describe()`): un campo non supportato dal mondo o di
 * sola lettura diventa disabilitato (e senza obbligatorietà), con un suggerimento che spiega perché.
 * I campi senza descrittore restano invariati (pachimud non cambia).
 *
 * @param rows - righe del form
 * @param resource - tipo di risorsa (`zone`, `room`, `mob`, `object`)
 * @param fieldOf - ricerca dei descrittori
 * @param t - traduzione
 * @returns nuove righe (le definizioni non vengono modificate)
 */
export function applyDescriptors(
  rows: IFieldRow[],
  resource: string,
  fieldOf: FieldLookup,
  t: (key: string) => string,
): IFieldRow[] {
  return rows.map((row) =>
    row.map((def) => {
      const descriptor = fieldOf(resource, def.field)
      if (!descriptor) return def
      if (descriptor.unsupported) {
        return { ...def, disable: true, readonly: true, required: false, hint: t('worlds.unsupportedField') }
      }
      if (descriptor.readOnly && descriptor.name !== 'id') {
        return { ...def, disable: true, readonly: true, hint: def.hint ?? t('worlds.readOnlyField') }
      }
      return def
    }),
  )
}

/**
 * Nomi ammessi per un campo `flags`/`enum` secondo il suo descrittore (`enum` = chiave di `/api/meta/enums`).
 *
 * @param enums - risposta di `GET /api/meta/enums`
 * @param descriptor - descrittore del campo
 * @returns i nomi (etichette) delle opzioni, vuoto se il campo non ha un elenco noto
 */
export function enumNames(enums: Record<string, unknown> | undefined, descriptor: IFieldDescriptor | undefined): FlagNames {
  const list = descriptor?.enum ? enums?.[descriptor.enum] : undefined
  const options = Array.isArray(list) ? (list as IFlagOption[]) : []
  const names: FlagNames = options.map((option) => option.label)
  // un catalogo (pachimud) spiega i flag: descrizione per lingua, alias, origine e se il gioco li usa davvero
  if (options.some((option) => option.description)) {
    names.details = Object.fromEntries(options.map((o) => [o.label, o as IFlagDetail]))
  }
  return names
}

/**
 * Definizione di un campo "flag": con un elenco di nomi noti (mondo con tabelle di flag, es. ROM) è un
 * selettore multiplo filtrabile, altrimenti l'elenco libero di chip (pachimud).
 *
 * @param base - campo, etichetta ed eventuale suggerimento
 * @param names - nomi ammessi (da {@link enumNames})
 */
export function flagsFieldDef(base: { field: string; label: string; hint?: string }, names: FlagNames): IFieldDef {
  return names.length
    ? { ...base, component: markRaw(EnumFlagsField), options: names, details: names.details }
    : { ...base, component: markRaw(FlagsField) }
}
