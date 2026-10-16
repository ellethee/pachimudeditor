import { markRaw } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { mdiContentCopy, mdiMapMarkerRadius, mdiPencil } from '@quasar/extras/mdi-v7'
import { PachiEditDialog } from '@ilpachi/pachi-kit/edit-dialog'
import type { AwaitableData, ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import { applyDescriptors } from '../../shared/helpers/descriptor-rows'
import { createExtraEditor } from '../../shared/helpers/extra-fields'
import { LOCKED_DIALOG_CLASS, guardOf, guardSection } from '../../shared/helpers/record-guard'
import { useWorld } from '../../shared/helpers/world-state'
import type { PachiTable2Api } from '@ilpachi/pachi-kit/table'
import { cloneZone, createZone, getNextZoneVnum } from '../services/zones-api'
import { useZonesStore } from '../stores/use-zones-store'
import type { IZone, IZoneCloneInput, IZoneInput } from '../types/zones'
import { describeError } from '../utils/errors'
import { buildCloneFieldRows, buildZoneFieldRows } from '../utils/zone-fields'

/** Opzioni per le richieste i cui errori sono mostrati dal dialogo di modifica (niente dialogo globale). */
const SILENT = { meta: { autoError: false } }

/**
 * Dialoghi della pagina zone: creazione, modifica, clonazione ed eliminazione.
 * Va chiamato in `setup()`.
 * @returns le azioni da collegare alla tabella
 */
export function useZoneDialogs() {
  const { t, te } = useI18n()
  const $q = useQuasar()
  const store = useZonesStore()
  const { readOnly, fieldOf, resourceOf, extraFieldsOf, declaresExtra } = useWorld()

  /**
   * Controlla i range incrociati (non esprimibili come regola di un singolo campo).
   * @param body dati del form
   * @returns messaggio d'errore, o `null` se validi
   */
  function validateRanges(body: IZoneInput): string | null {
    if (body.bottomVnum > body.topVnum) return t('zones.validation.vnumRange')
    if (body.minLevel > body.maxLevel) return t('zones.validation.levelRange')
    return null
  }

  /**
   * Apre il dialogo di creazione/modifica.
   * @param initial valori iniziali (con `id` in modifica)
   * @param api API della tabella usata per salvare
   */
  async function openZoneDialog(initial: Partial<IZone>, api: PachiTable2Api<IZone>): Promise<void> {
    const enums = await store.ensureEnums()
    const editing = initial.id !== undefined
    const guard = guardOf(initial.extra)
    const locked = readOnly.value || guard.corrupted
    // mondi che aggiungono le zone solo in coda: vnum e range di partenza sono calcolati dal backend
    const atEnd = !editing && resourceOf('zone')?.createAtEnd === true
    const rows = buildZoneFieldRows(t, enums.zoneResetMode, editing || atEnd)
    if (atEnd) {
      rows.ranges[0] = rows.ranges[0]!.map((def) =>
        def.field === 'bottomVnum' ? { ...def, disable: true, readonly: true, hint: t('worlds.createAtEnd') } : def,
      )
    }
    const extraEditor = createExtraEditor({
      t,
      te,
      descriptors: extraFieldsOf('zone'),
      declared: declaresExtra('zone'),
      readonly: locked,
      extra: initial.extra,
      enums: enums as unknown as Record<string, unknown>,
      order: 30,
    })
    const sections: ISectionDefinition[] = [
      {
        key: 'general',
        title: t('zones.form.sectionGeneral'),
        component: markRaw(FieldsSection),
        props: { rows: applyDescriptors(rows.general, 'zone', fieldOf, t) },
        initialValue: initial,
        order: 10,
        container: { type: 'card', flat: true, bordered: true, class: 'q-pa-md q-mb-md', style: 'flex: none' },
      },
      {
        key: 'ranges',
        title: t('zones.form.sectionRanges'),
        component: markRaw(FieldsSection),
        props: { rows: applyDescriptors(rows.ranges, 'zone', fieldOf, t) },
        initialValue: initial,
        order: 20,
        container: { type: 'card', flat: true, bordered: true, class: 'q-pa-md', style: 'flex: none' },
      },
    ]
    if (extraEditor) sections.push(extraEditor.section)
    const banner = guardSection(guard)
    if (banner) sections.unshift(banner)
    $q.dialog({
      component: PachiEditDialog,
      componentProps: {
        title: editing ? t('zones.form.editTitle') : t('zones.form.createTitle'),
        icon: editing ? mdiPencil : mdiMapMarkerRadius,
        sections,
        avoidHideWithChanges: true,
        commonProps: locked ? { readonly: true } : {},
        cardClass: guard.corrupted ? LOCKED_DIALOG_CLASS : '',
        width: '640px',
        maxWidth: '95vw',
      },
    }).onOk(async ({ data, onSuccess, onError }: AwaitableData) => {
      if (locked) {
        onError(new Error(t('worlds.readOnlyHint')))
        return
      }
      const body = { ...(data.sections.general as object), ...(data.sections.ranges as object) } as IZoneInput
      // `extra` (campi specifici del mondo) solo con le chiavi cambiate
      const extra = extraEditor?.collect(data.sections.extra)
      if (extra) body.extra = extra
      const rangeError = validateRanges(body)
      if (rangeError) {
        onError(new Error(rangeError))
        return
      }
      try {
        if (editing) await api.updateRecord({ ...body, id: initial.id as number }, SILENT)
        else await createZone(body)
        // ricarica sempre: in un mondo su file l'id coincide col vnum minimo e cambia se cambia `bottomVnum`
        await api.reload()
        onSuccess()
      } catch (error) {
        onError(new Error(await describeError(error)))
      }
    })
  }

  /**
   * Nuova zona: vnum e range liberi vengono proposti in anticipo (se la richiesta fallisce il form parte vuoto).
   * @param api API della tabella
   */
  async function openCreate(api: PachiTable2Api<IZone>): Promise<void> {
    const enums = await store.ensureEnums()
    const initial: Partial<IZone> = {
      name: '',
      builder: '',
      bottomVnum: 0,
      topVnum: 0,
      minLevel: 1,
      maxLevel: 1,
      lifespanMinutes: 30,
      resetMode: enums.zoneResetMode[1]?.value ?? enums.zoneResetMode[0]?.value ?? 0,
      enabled: true,
    }
    try {
      const next = await getNextZoneVnum(undefined, true)
      Object.assign(initial, next)
    } catch {
      // nessun suggerimento: l'utente inserisce vnum e range a mano
    }
    await openZoneDialog(initial, api)
  }

  /**
   * Modifica una zona esistente.
   * @param zone riga da modificare
   * @param api API della tabella
   */
  function openEdit(zone: IZone, api: PachiTable2Api<IZone>): Promise<void> {
    return openZoneDialog(zone, api)
  }

  /**
   * Apre il dialogo di clonazione (nuovo vnum proposto, nome con suffisso).
   * @param zone zona sorgente
   * @param api API della tabella (per ricaricare)
   */
  async function openClone(zone: IZone, api: PachiTable2Api<IZone>): Promise<void> {
    let suggested: number | null = null
    try {
      suggested = (await getNextZoneVnum(undefined, true)).vnum
    } catch {
      // nessun suggerimento
    }
    const initial = { vnum: null, name: `${zone.name} ${t('zones.clone.nameSuffix')}`, copyResetCommands: false }
    const sections: ISectionDefinition[] = [
      {
        key: 'main',
        title: t('zones.clone.title'),
        component: markRaw(FieldsSection),
        props: { rows: buildCloneFieldRows(t, suggested) },
        initialValue: initial,
      },
    ]
    $q.dialog({
      component: PachiEditDialog,
      componentProps: { title: t('zones.clone.title'), icon: mdiContentCopy, sections, width: '480px', maxWidth: '95vw' },
    }).onOk(async ({ data, onSuccess, onError }: AwaitableData) => {
      try {
        await cloneZone(zone.id, data.sections.main as IZoneCloneInput)
        await api.reload()
        onSuccess()
        $q.notify({ type: 'positive', message: t('zones.clone.done') })
      } catch (error) {
        onError(new Error(await describeError(error)))
      }
    })
  }

  /**
   * Elimina una zona dopo conferma. Un errore (es. zona non vuota) è già mostrato dal dialogo globale del client HTTP.
   * @param zone zona da eliminare
   * @param api API della tabella
   */
  async function deleteZone(zone: IZone, api: PachiTable2Api<IZone>): Promise<void> {
    await api.confirmAction(t('zones.deleteConfirm', { name: zone.name, vnum: zone.vnum }), async () => {
      try {
        await api.deleteRecord(zone)
      } catch {
        // già segnalato dal client HTTP
      }
    })
  }

  return { openCreate, openEdit, openClone, deleteZone }
}
