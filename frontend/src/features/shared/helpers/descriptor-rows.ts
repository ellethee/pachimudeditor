import { markRaw } from 'vue'
import type { IFieldDef, IFieldRow } from '@ilpachi/pachi-kit/fields'
import EnumFlagsField from '../components/EnumFlagsField.vue'
import FlagsField from '../components/FlagsField.vue'
import type { IFieldDescriptor } from '../types/worlds'

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
export function enumNames(enums: Record<string, unknown> | undefined, descriptor: IFieldDescriptor | undefined): string[] {
  const list = descriptor?.enum ? enums?.[descriptor.enum] : undefined
  return Array.isArray(list) ? (list as { label: string }[]).map((option) => option.label) : []
}

/**
 * Definizione di un campo "flag": con un elenco di nomi noti (mondo con tabelle di flag, es. ROM) è un
 * selettore multiplo filtrabile, altrimenti l'elenco libero di chip (pachimud).
 *
 * @param base - campo, etichetta ed eventuale suggerimento
 * @param names - nomi ammessi (da {@link enumNames})
 */
export function flagsFieldDef(base: { field: string; label: string; hint?: string }, names: string[]): IFieldDef {
  return names.length
    ? { ...base, component: markRaw(EnumFlagsField), options: names }
    : { ...base, component: markRaw(FlagsField) }
}
