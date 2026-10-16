<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <h1 class="text-h5 q-my-none">{{ t('objects.title') }}</h1>
      <q-select
        v-model="selectedZoneId"
        :options="zones"
        option-value="id"
        option-label="name"
        emit-value
        map-options
        :label="t('objects.zone')"
        :loading="zonesLoading"
        style="min-width: 260px"
        dense
        outlined
      />
    </div>

    <pachi-error-state
      v-if="loadError"
      :title="t('objects.errorTitle')"
      :description="t('objects.errorDescription')"
      :primary-label="t('objects.retry')"
      @primary="loadLookups"
    />
    <pachi-empty-state
      v-else-if="!zonesLoading && zones.length === 0"
      :icon="mdiInbox"
      :title="t('objects.noZonesTitle')"
      :description="t('objects.noZonesDescription')"
    />
    <pachi-table2
      v-else-if="selectedZoneId !== undefined"
      ref="table"
      :url="OBJECTS_URL"
      :columns="columns"
      :extra-params="extraParams"
      :initial-sort="[{ column: 'vnum', direction: 'asc' }]"
      use-col-actions="emit-delete"
      :can-edit="allowRow"
      :can-delete="allowDelete"
      error-banner
      dense
      @pt2:edit-item="openEdit"
      @pt2:delete-item="confirmDelete"
      @row-dblclick="(_evt: Event, row: IObjects) => openEdit(row)"
    >
      <template #toolbar-actions="{ api }">
        <q-btn v-if="!readOnly" color="primary" :icon="mdiPlus" :label="t('objects.new')" @click="openCreate(api)" />
        <q-btn flat round :icon="mdiRefresh" :aria-label="t('objects.reload')" @click="api.reload()" />
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiInbox, mdiPencil, mdiPlus, mdiRefresh } from '@quasar/extras/mdi-v7'
import { PachiEmptyState, PachiErrorState } from '@ilpachi/pachifastquasar'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import type { PachiTable2Api, PachiTable2Exposed } from '@ilpachi/pachi-kit/table'
import { PachiEditDialog } from '@ilpachi/pachi-kit/edit-dialog'
import type { AwaitableData, ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import { describeError } from '../helpers/describe-error'
import InstancesSection from '../../instances/components/InstancesSection.vue'
import { applyDescriptors, enumNames } from '../../shared/helpers/descriptor-rows'
import { createExtraEditor } from '../../shared/helpers/extra-fields'
import { LOCKED_DIALOG_CLASS, guardOf, guardSection } from '../../shared/helpers/record-guard'
import { useWorld } from '../../shared/helpers/world-state'
import { whenReady } from '../../shared/helpers/when-ready'
import { localizeEnums } from '../../shared/helpers/enum-labels'
import { buildGeneralRows, buildStatsRows } from '../helpers/field-rows'
import { OBJECTS_URL, getEnums, getObject, getObjectUsage, listZones, nextObjectVnum } from '../services/objects-api'
import type { IObjectEnums, IObjects, IObjectsInput, IZoneRef } from '../types/objects'

const { t, te } = useI18n()
const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const { readOnly, supports, fieldOf, extraFieldsOf, declaresExtra } = useWorld()

/** Tutte le righe si aprono in modifica (in sola lettura il form è bloccato); serve anche a tipizzare la tabella su `IObjects`. */
const allowRow = (_row: IObjects): boolean => true
/** Eliminabili solo in un mondo scrivibile. */
const allowDelete = (row: IObjects): boolean => !readOnly.value && !guardOf(row.extra).corrupted

const table = ref<PachiTable2Exposed<IObjects> | null>(null)
const zones = ref<IZoneRef[]>([])
const zonesLoading = ref(true)
const loadError = ref(false)
const selectedZoneId = ref<number>()
const enums = ref<IObjectEnums>()
/** Risposta grezza di `/api/meta/enums` (comprende anche le tabelle specifiche del mondo, es. `romExtraFlags`). */
const enumsRaw = computed(() => enums.value as unknown as Record<string, unknown> | undefined)

/** Filtro esatto per zona inviato alla tabella. */
const extraParams = computed<Record<string, unknown>>(() =>
  selectedZoneId.value !== undefined ? { zoneId: selectedZoneId.value } : {},
)

/**
 * Etichetta del tipo di oggetto.
 *
 * @param objectType - valore intero del tipo
 */
function typeLabel(objectType: number): string {
  return enums.value?.objectType.find((option) => option.value === objectType)?.label ?? String(objectType)
}

const columns = computed<QTableColumn<IObjects>[]>(() => [
  { name: 'vnum', label: t('objects.columns.vnum'), field: 'vnum', align: 'left', sortable: true },
  {
    name: 'shortDescription',
    label: t('objects.columns.shortDescription'),
    field: 'shortDescription',
    align: 'left',
  },
  {
    name: 'objectType',
    label: t('objects.columns.objectType'),
    field: (row: IObjects) => typeLabel(row.objectType),
    align: 'left',
    sortable: true,
  },
])

/** Carica zone ed enum (una volta, alla creazione della pagina). */
async function loadLookups(): Promise<void> {
  loadError.value = false
  zonesLoading.value = true
  try {
    const [zoneList, enumList] = await Promise.all([listZones(), getEnums()])
    zones.value = zoneList
    enums.value = withBuffTargets(localizeEnums(enumList))
    const wanted = Number(route.query.zoneId)
    selectedZoneId.value =
      zoneList.find((zone) => zone.id === wanted)?.id ?? selectedZoneId.value ?? zoneList[0]?.id
  } catch {
    loadError.value = true
  } finally {
    zonesLoading.value = false
  }
  if (!loadError.value) await openFromQuery()
}

/**
 * Bersagli degli affects: se il backend non li espone ma il mondo ha una tabella di apply (ROM:
 * `romAffectApply`), si usano i suoi nomi come chiavi del dizionario `affects`.
 *
 * @param list - enum localizzati del backend
 */
function withBuffTargets(list: IObjectEnums): IObjectEnums {
  if (list.buffTarget?.length) return list
  const apply = (list as unknown as Record<string, { label: string }[] | undefined>).romAffectApply
  return apply?.length ? { ...list, buffTarget: apply.map((option) => ({ value: option.label, label: option.label })) } : list
}

/**
 * Deep-link `?objectId=`: seleziona la zona dell'oggetto e ne apre l'editor (poi toglie il parametro). Un id
 * inesistente lascia semplicemente l'elenco.
 */
async function openFromQuery(): Promise<void> {
  const id = Number(route.query.objectId)
  if (route.query.objectId === undefined || !Number.isFinite(id)) return
  try {
    const object = await getObject(id)
    if (zones.value.some((zone) => zone.id === object.zoneId)) selectedZoneId.value = object.zoneId
    await router.replace({ path: route.path, query: { zoneId: String(object.zoneId) } })
    const api = await whenReady(() => table.value?.api)
    await openDialog(api, object)
  } catch {
    // oggetto inesistente o non leggibile: resta l'elenco
  }
}

/**
 * Valori iniziali del form per un nuovo oggetto.
 *
 * @param zoneId - zona di destinazione
 */
function emptyObject(zoneId: number): IObjectsInput {
  return {
    vnum: 0,
    zoneId,
    keywords: '',
    shortDescription: '',
    longDescription: '',
    actionDescription: null,
    objectType: enums.value?.objectType[0]?.value ?? 0,
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
 * Apre il dialog di creazione/modifica.
 *
 * @param api - API della tabella (per salvare e ricaricare)
 * @param record - oggetto da modificare; assente per la creazione
 */
async function openDialog(api: PachiTable2Api<IObjects>, record?: IObjects): Promise<void> {
  const zoneId = record?.zoneId ?? selectedZoneId.value
  if (zoneId === undefined) return
  const initial: Record<string, unknown> = record ? { ...record } : { ...emptyObject(zoneId) }
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
    enums: enumsRaw.value,
    order: 30,
  })
  const sections: ISectionDefinition[] = [
    {
      key: 'general',
      title: t('objects.sections.general'),
      component: markRaw(FieldsSection),
      props: { rows: rowsOf(buildGeneralRows(t, enums.value, zoneId, !!record)) },
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
            enums.value,
            enumNames(enumsRaw.value, fieldOf('object', 'extraFlags')),
            enumNames(enumsRaw.value, fieldOf('object', 'wearFlags')),
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
  $q.dialog({
    component: PachiEditDialog,
    componentProps: {
      title: record ? t('objects.editTitle') : t('objects.createTitle'),
      icon: record ? mdiPencil : mdiPlus,
      sections,
      avoidHideWithChanges: true,
      commonProps: locked ? { readonly: true } : {},
      cardClass: guard.corrupted ? LOCKED_DIALOG_CLASS : '',
      width: '720px',
      maxWidth: '95vw',
    },
  }).onOk(async ({ data, onSuccess, onError }: AwaitableData) => {
    if (locked) {
      onError(new Error(t('worlds.readOnlyHint')))
      return
    }
    const body = {
      ...(data.sections.general as Record<string, unknown>),
      ...(data.sections.stats as Record<string, unknown>),
    } as Partial<IObjectsInput>
    // il campo opzionale vuoto si invia come null
    if (body.actionDescription === '') body.actionDescription = null
    // `extra` (campi specifici del mondo) solo con le chiavi cambiate
    const extra = extraEditor?.collect(data.sections.extra)
    if (extra) body.extra = extra
    try {
      if (record) {
        // PUT = patch parziale: il vnum e la zona non si cambiano
        const { vnum: _vnum, ...patch } = body
        await api.Put<IObjects>(`/${record.id}`, patch, { cacheFor: 0, meta: { autoError: false } })
        await api.reload()
      } else {
        // POST senza slash finale (createRecord della tabella posterebbe su `{url}/`, che il backend non espone)
        await api.Post<IObjects>('', { ...initial, ...body, zoneId }, { cacheFor: 0, meta: { autoError: false } })
        await api.reload()
      }
      onSuccess()
    } catch (error) {
      onError(new Error(await describeError(error)))
    }
  })
}

/** Gestore dell'edit della tabella (pulsante riga o doppio click). */
function openEdit(row: IObjects, api?: PachiTable2Api<IObjects>): void {
  const tableApi = api ?? table.value?.api
  if (tableApi) openDialog(tableApi, row)
}

/** Apre il dialog di creazione. */
function openCreate(api: PachiTable2Api<IObjects>): void {
  openDialog(api)
}

/**
 * Chiede conferma (segnalando i reset che lo referenziano) e elimina l'oggetto.
 *
 * @param row - oggetto da eliminare
 * @param api - API della tabella
 */
async function confirmDelete(row: IObjects, api: PachiTable2Api<IObjects>): Promise<void> {
  const usage = await getObjectUsage(row.id)
  const zoneNames = [...new Set(usage.map((item) => item.zoneName))].join(', ')
  const warning =
    usage.length > 0 ? ' ' + t('objects.delete.usageWarning', { count: usage.length, zones: zoneNames }) : ''
  $q.dialog({
    title: t('objects.delete.title'),
    message: t('objects.delete.message', { name: row.shortDescription, vnum: row.vnum }) + warning,
    cancel: true,
    persistent: true,
  }).onOk(() => {
    // gli errori (es. 409 in uso nei reset) li mostra già il dialog globale dell'HTTP client
    api.deleteRecord(row).catch(() => undefined)
  })
}

onMounted(loadLookups)
</script>
