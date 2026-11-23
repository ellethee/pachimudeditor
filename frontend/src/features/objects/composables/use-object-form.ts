import { markRaw } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import InstancesSection from '../../instances/components/InstancesSection.vue'
import { applyDescriptors, enumNames } from '../../shared/helpers/descriptor-rows'
import { localizeEnums } from '../../shared/helpers/enum-labels'
import { createExtraEditor } from '../../shared/helpers/extra-fields'
import { settleClearedFields } from '../../shared/helpers/optional-fields'
import { guardOf, guardSection } from '../../shared/helpers/record-guard'
import { useWorld } from '../../shared/helpers/world-state'
import { buildGeneralRows, buildStatsRows } from '../helpers/field-rows'
import { getEnums, nextObjectVnum } from '../services/objects-api'
import type { IObjectEnums, IObjects, IObjectsInput } from '../types/objects'

/**
 * Bersagli degli affects: se il backend non li espone ma il mondo ha una tabella di apply (ROM:
 * `romAffectApply`), si usano i suoi nomi come chiavi del dizionario `affects`.
 *
 * @param list - enum localizzati del backend
 */
export function withBuffTargets(list: IObjectEnums): IObjectEnums {
  if (list.buffTarget?.length) return list
  const apply = (list as unknown as Record<string, { label: string }[] | undefined>).romAffectApply
  return apply?.length ? { ...list, buffTarget: apply.map((option) => ({ value: option.label, label: option.label })) } : list
}

/** Carica gli enum degli oggetti (localizzati, con i bersagli degli affects). */
export async function loadObjectEnums(): Promise<IObjectEnums> {
  return withBuffTargets(localizeEnums(await getEnums()))
}

/**
 * Valori iniziali del form per un nuovo oggetto.
 *
 * @param zoneId - zona di destinazione
 * @param enums - enum del backend
 */
function emptyObject(zoneId: number, enums: IObjectEnums): IObjectsInput {
  return {
    vnum: 0,
    zoneId,
    keywords: '',
    shortDescription: '',
    longDescription: '',
    actionDescription: null,
    objectType: enums.objectType[0]?.value ?? 0,
    weight: 0,
    cost: 0,
    rent: 0,
    value0: null,
    value1: null,
    value2: null,
    value3: null,
    extraFlags: [],
    wearFlags: [],
    affects: {},
  }
}

/**
 * Form di un oggetto (sezioni, blocco in sola lettura, raccolta dei dati): lo usano il dialogo di creazione e la
 * pagina di dettaglio. Da chiamare in `setup()`.
 */
export function useObjectForm() {
  const { t, te } = useI18n()
  const { readOnly, supports, fieldOf, extraFieldsOf, declaresExtra } = useWorld()

  /**
   * Prepara il form.
   *
   * @param enums - enum del backend
   * @param record - oggetto da modificare; assente per la creazione
   * @param createZoneId - zona del nuovo oggetto (solo creazione)
   */
  async function prepareObjectForm(enums: IObjectEnums, record?: IObjects, createZoneId?: number) {
    const zoneId = (record?.zoneId ?? createZoneId) as number
    const enumsRaw = enums as unknown as Record<string, unknown>
    const initial: Record<string, unknown> = record ? { ...record } : { ...emptyObject(zoneId, enums) }
    if (!record) {
      // creazione: propone subito il prossimo vnum libero della zona (l'utente può cambiarlo)
      try {
        initial.vnum = await nextObjectVnum(zoneId)
      } catch {
        // resta 0: il pulsante del campo vnum permette di riprovare
      }
    }
    const guard = guardOf(record?.extra)
    const locked = readOnly.value || guard.corrupted
    const rowsOf = (rows: IFieldRow[]): IFieldRow[] =>
      guard.corrupted
        ? applyDescriptors(rows, 'object', fieldOf, t).map((row) => row.map((def) => ({ ...def, disable: true, readonly: true })))
        : applyDescriptors(rows, 'object', fieldOf, t)
    const extraEditor = createExtraEditor({
      t,
      te,
      descriptors: extraFieldsOf('object'),
      declared: declaresExtra('object'),
      readonly: locked,
      extra: record?.extra,
      enums: enumsRaw,
      order: 30,
    })
    const sections: ISectionDefinition[] = [
      {
        key: 'general',
        title: t('objects.sections.general'),
        component: markRaw(FieldsSection),
        props: { rows: rowsOf(buildGeneralRows(t, enums, zoneId, !!record)) },
        initialValue: initial,
        order: 10,
        container: { type: 'card', flat: true, bordered: true, class: 'q-pa-md q-mb-md' },
      },
      {
        key: 'stats',
        title: t('objects.sections.stats'),
        component: markRaw(FieldsSection),
        props: {
          rows: rowsOf(
            buildStatsRows(
              t,
              enums,
              enumNames(enumsRaw, fieldOf('object', 'extraFlags')),
              enumNames(enumsRaw, fieldOf('object', 'wearFlags')),
            ),
          ),
        },
        initialValue: initial,
        order: 20,
        container: { type: 'expansion', title: t('objects.sections.stats'), defaultOpened: true },
      },
    ]
    if (extraEditor) sections.push(extraEditor.section)
    const banner = guardSection(guard)
    if (banner) sections.unshift(banner)
    if (record && supports('supportsInstances') && !guard.corrupted) {
      sections.push({
        key: 'instances',
        title: t('worlds.instances'),
        component: markRaw(InstancesSection),
        props: { kind: 'object', prototypeId: record.id },
        initialValue: {},
        order: 40,
        container: { type: 'expansion', title: t('worlds.instances'), defaultOpened: false },
      })
    }

    /**
     * Unisce i risultati delle sezioni nel corpo da inviare.
     * @param results `data.sections` del dialogo / `getResults()` del form
     */
    function collect(results: Record<string, unknown>): Partial<IObjectsInput> {
      const body = {
        ...(results.general as Record<string, unknown>),
        ...(results.stats as Record<string, unknown>),
      } as Partial<IObjectsInput>
      // il campo opzionale vuoto si invia come null solo se l'oggetto salvato ne aveva uno
      settleClearedFields(body, record, ['actionDescription'])
      // `extra` (campi specifici del mondo) solo con le chiavi cambiate
      const extra = extraEditor?.collect(results.extra)
      if (extra) body.extra = extra
      return body
    }

    return { sections, locked, guard, initial, zoneId, collect }
  }

  return { prepareObjectForm }
}
