<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <h1 class="text-h5 q-my-none">{{ t('objects.title') }}</h1>
      <q-select
        v-model="selectedZoneId"
        :options="zoneOptions"
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

    <object-filters
      v-if="ready && !loadError"
      v-model="filters"
      :type-options="enums?.objectType ?? []"
      :wear-names="wearNames"
      :extra-names="extraNames"
      :apply-names="applyNames"
    />
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
      v-else-if="ready"
      ref="table"
      :url="OBJECTS_URL"
      :columns="columns"
      :extra-params="extraParams"
      :initial-sort="[]"
      use-col-actions="emit-delete"
      :can-edit="allowRow"
      :can-delete="allowDelete"
      error-banner
      dense
      @pt2:edit-item="openEdit"
      @pt2:delete-item="confirmDelete"
      @row-dblclick="(_evt: Event, row: IObjects) => openEdit(row)"
    >
      <template #error="{ error, retry }">
        <table-error :error="error" :retry="retry" />
      </template>
      <template #toolbar-actions="{ api }">
        <q-btn flat round :icon="mdiTableColumn" :aria-label="t('objects.columnsMenu.button')" data-test="columns-menu">
          <q-tooltip>{{ t('objects.columnsMenu.button') }}</q-tooltip>
          <q-menu>
            <q-list dense style="min-width: 200px">
              <q-item-label header>{{ t('objects.columnsMenu.title') }}</q-item-label>
              <q-item v-for="name in COLUMN_NAMES" :key="name" tag="label" v-ripple>
                <q-item-section side>
                  <q-checkbox
                    dense
                    :model-value="visibleColumns.includes(name)"
                    :disable="visibleColumns.length === 1 && visibleColumns.includes(name)"
                    @update:model-value="(on: boolean) => toggleColumn(name, on)"
                  />
                </q-item-section>
                <q-item-section>{{ t(`objects.columns.${name}`) }}</q-item-section>
              </q-item>
              <q-separator />
              <q-item clickable v-close-popup @click="resetColumns">
                <q-item-section>{{ t('objects.columnsMenu.reset') }}</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
        <q-btn v-if="!readOnly" color="primary" :icon="mdiPlus" :label="t('objects.new')" @click="openCreate(api)" />
        <q-btn flat round :icon="mdiRefresh" :aria-label="t('objects.reload')" @click="api.reload()" />
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiInbox, mdiPencil, mdiPlus, mdiRefresh, mdiTableColumn } from '@quasar/extras/mdi-v7'
import { PachiEmptyState, PachiErrorState } from '@ilpachi/pachifastquasar'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import type { PachiTable2Api, PachiTable2Exposed } from '@ilpachi/pachi-kit/table'
import { PachiEditDialog } from '@ilpachi/pachi-kit/edit-dialog'
import type { AwaitableData } from '@ilpachi/pachi-kit/edit-dialog'
import { describeError } from '../helpers/describe-error'
import { applyDescriptors, enumNames } from '../../shared/helpers/descriptor-rows'
import { LOCKED_DIALOG_CLASS, guardOf } from '../../shared/helpers/record-guard'
import { useWorld } from '../../shared/helpers/world-state'
import { localizeEnums } from '../../shared/helpers/enum-labels'
import { useObjectForm, withBuffTargets } from '../composables/use-object-form'
import { OBJECTS_URL, getEnums, getObjectUsage, listZones } from '../services/objects-api'
import type { IObjectEnums, IObjects, IObjectsInput, IZoneRef } from '../types/objects'
import TableError from '../../shared/components/TableError.vue'
import ObjectFilters from '../components/ObjectFilters.vue'
import ZonePickDialog from '../../shared/components/ZonePickDialog.vue'
import {
  COLUMN_NAMES,
  FILTER_QUERY_KEYS,
  defaultColumns,
  emptyFilters,
  filtersFromQuery,
  filtersToParams,
  loadColumns,
  saveColumns,
  summarize,
  summarizeAffects,
} from '../helpers/list-query'
import type { IObjectFilters } from '../helpers/list-query'

const { t, te } = useI18n()
const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const { readOnly, fieldOf } = useWorld()
const { prepareObjectForm } = useObjectForm()

/** Tutte le righe si aprono in modifica (in sola lettura il form è bloccato); serve anche a tipizzare la tabella su `IObjects`. */
const allowRow = (_row: IObjects): boolean => true
/** Eliminabili solo in un mondo scrivibile. */
const allowDelete = (row: IObjects): boolean => !readOnly.value && !guardOf(row.extra).corrupted

const table = ref<PachiTable2Exposed<IObjects> | null>(null)
const zones = ref<IZoneRef[]>([])
const zonesLoading = ref(true)
const loadError = ref(false)
/** Valore del selettore di zona per «tutte le zone» (gli id reali sono >= 0). */
const ALL_ZONES = -1
const selectedZoneId = ref<number>(ALL_ZONES)
/** `true` a lookup caricati: la tabella può partire con zona e filtri letti dall'URL. */
const ready = ref(false)
const filters = ref<IObjectFilters>(emptyFilters())
const enums = ref<IObjectEnums>()
/** Risposta grezza di `/api/meta/enums` (comprende anche le tabelle specifiche del mondo, es. `romExtraFlags`). */
const enumsRaw = computed(() => enums.value as unknown as Record<string, unknown> | undefined)

/** Opzioni del selettore: «Tutte le zone» e poi le zone. */
const zoneOptions = computed(() => [{ id: ALL_ZONES, name: t('objects.allZones') }, ...zones.value])

/** Filtro per zona (se scelta) e filtri sulle statistiche inviati alla tabella. */
const extraParams = computed<Record<string, unknown>>(() => ({
  ...(selectedZoneId.value !== ALL_ZONES ? { zoneId: selectedZoneId.value } : {}),
  ...filtersToParams(filters.value),
}))

/** Nomi noti dei flag di indossabilità / extra / apply del mondo (vuoto: inserimento libero nei filtri). */
const wearNames = computed(() => enumNames(enumsRaw.value, fieldOf('object', 'wearFlags')))
const extraNames = computed(() => enumNames(enumsRaw.value, fieldOf('object', 'extraFlags')))
const applyNames = computed(() => (enums.value?.buffTarget ?? []).map((option) => String(option.value)))

/** Colonne visibili: scelta salvata dal viewer, altrimenti pochi default (telefono) o i principali. */
const visibleColumns = ref<string[]>(loadColumns() ?? defaultColumns($q.screen.lt.sm))

/**
 * Mostra o nasconde una colonna e salva la scelta.
 *
 * @param name - nome della colonna
 * @param on - `true` per mostrarla
 */
function toggleColumn(name: string, on: boolean): void {
  visibleColumns.value = COLUMN_NAMES.filter((column) => (column === name ? on : visibleColumns.value.includes(column)))
  saveColumns(visibleColumns.value)
}

/** Ripristina le colonne di default. */
function resetColumns(): void {
  visibleColumns.value = defaultColumns($q.screen.lt.sm)
  saveColumns(visibleColumns.value)
}

/**
 * Nome della zona.
 *
 * @param zoneId - id della zona
 */
function zoneName(zoneId: number): string {
  return zones.value.find((zone) => zone.id === zoneId)?.name ?? String(zoneId)
}

/**
 * Etichetta del tipo di oggetto.
 *
 * @param objectType - valore intero del tipo
 */
function typeLabel(objectType: number): string {
  return enums.value?.objectType.find((option) => option.value === objectType)?.label ?? String(objectType)
}

/** Tutte le colonne (il `name` è la chiave di `orderBy` del backend); mostrate solo quelle scelte. */
const allColumns = computed<QTableColumn<IObjects>[]>(() => {
  const num = (name: keyof IObjects & string): QTableColumn<IObjects> => ({
    name,
    label: t(`objects.columns.${name}`),
    field: name,
    align: 'right',
    sortable: true,
    format: (value: number | null) => (value === null || value === undefined ? '' : String(value)),
  })
  const clip = 'ellipsis'
  return [
    { name: 'vnum', label: t('objects.columns.vnum'), field: 'vnum', align: 'left', sortable: true },
    { name: 'shortDescription', label: t('objects.columns.shortDescription'), field: 'shortDescription', align: 'left', sortable: true },
    { name: 'zoneId', label: t('objects.columns.zoneId'), field: (row) => zoneName(row.zoneId), align: 'left', sortable: true },
    { name: 'objectType', label: t('objects.columns.objectType'), field: (row) => typeLabel(row.objectType), align: 'left', sortable: true },
    num('weight'),
    num('cost'),
    num('rent'),
    num('value0'),
    num('value1'),
    num('value2'),
    num('value3'),
    {
      name: 'wearFlags',
      label: t('objects.columns.wearFlags'),
      field: (row) => summarize(row.wearFlags),
      align: 'left',
      classes: clip,
      style: 'max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap',
    },
    {
      name: 'affects',
      label: t('objects.columns.affects'),
      field: (row) => summarizeAffects(row.affects),
      align: 'left',
      style: 'max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap',
    },
  ]
})
const columns = computed(() => allColumns.value.filter((column) => visibleColumns.value.includes(column.name)))

/** Carica zone ed enum (una volta, alla creazione della pagina). */
async function loadLookups(): Promise<void> {
  loadError.value = false
  zonesLoading.value = true
  try {
    const [zoneList, enumList] = await Promise.all([listZones(), getEnums()])
    zones.value = zoneList
    enums.value = withBuffTargets(localizeEnums(enumList))
    applyQuery()
  } catch {
    loadError.value = true
  } finally {
    zonesLoading.value = false
  }
  ready.value = !loadError.value
  if (!loadError.value) await openFromQuery()
}

/** Zona e filtri dall'URL (zona sconosciuta o assente: tutte le zone). */
function applyQuery(): void {
  const wanted = route.query.zoneId === undefined ? NaN : Number(route.query.zoneId)
  selectedZoneId.value = zones.value.find((zone) => zone.id === wanted)?.id ?? ALL_ZONES
  filters.value = filtersFromQuery(route.query)
}

/** Query string corrispondente allo stato (zona e filtri) mantenendo gli altri parametri dell'URL. */
function stateQuery(): Record<string, string> {
  const base = Object.fromEntries(
    Object.entries(route.query).filter(([key]) => key !== 'zoneId' && !FILTER_QUERY_KEYS.includes(key)),
  ) as Record<string, string>
  const zone = selectedZoneId.value !== ALL_ZONES ? { zoneId: String(selectedZoneId.value) } : {}
  const entries = Object.entries(filtersToParams(filters.value, true)).map(([key, value]) => [key, String(value)])
  return { ...base, ...zone, ...Object.fromEntries(entries) }
}

/** Riscrive l'URL con lo stato corrente (sostituisce la voce di cronologia solo se qualcosa è cambiato). */
function syncUrl(): void {
  if (!ready.value) return
  const next = stateQuery()
  const same = JSON.stringify(Object.entries(next).sort()) === JSON.stringify(Object.entries(route.query).sort())
  if (!same) void router.replace({ path: route.path, query: next })
}

watch([selectedZoneId, filters], syncUrl, { deep: true })
// navigazione indietro/avanti o link condiviso: lo stato segue l'URL
watch(
  () => route.query,
  () => {
    if (!ready.value) return
    const parsed = filtersFromQuery(route.query)
    const zone = Number(route.query.zoneId)
    const nextZone = zones.value.some((z) => z.id === zone) ? zone : ALL_ZONES
    if (nextZone === selectedZoneId.value && JSON.stringify(parsed) === JSON.stringify(filters.value)) return
    applyQuery()
  },
)

/** Deep-link `?objectId=`: apre il dettaglio dell'oggetto. Un id inesistente lascia semplicemente l'elenco. */
async function openFromQuery(): Promise<void> {
  const id = Number(route.query.objectId)
  if (route.query.objectId === undefined || !Number.isFinite(id)) return
  await router.replace(`/objects/${id}`)
}

/**
 * Apre il dialog di creazione.
 *
 * @param api - API della tabella (per salvare e ricaricare)
 * @param zoneId - zona del nuovo oggetto
 */
async function openDialog(api: PachiTable2Api<IObjects>, zoneId: number): Promise<void> {
  if (zoneId === ALL_ZONES || !enums.value) return
  const form = await prepareObjectForm(enums.value, undefined, zoneId)
  $q.dialog({
    component: PachiEditDialog,
    componentProps: {
      title: t('objects.createTitle'),
      icon: mdiPlus,
      sections: form.sections,
      avoidHideWithChanges: true,
      commonProps: form.locked ? { readonly: true } : {},
      cardClass: form.guard.corrupted ? LOCKED_DIALOG_CLASS : '',
      width: '720px',
      maxWidth: '95vw',
    },
  }).onOk(async ({ data, onSuccess, onError }: AwaitableData) => {
    if (form.locked) {
      onError(new Error(t('worlds.readOnlyHint')))
      return
    }
    try {
      // POST senza slash finale (createRecord della tabella posterebbe su `{url}/`, che il backend non espone)
      await api.Post<IObjects>('', { ...form.initial, ...form.collect(data.sections), zoneId }, { cacheFor: 0, meta: { autoError: false } })
      await api.reload()
      onSuccess()
    } catch (error) {
      onError(new Error(await describeError(error)))
    }
  })
}

/** Gestore dell'edit della tabella (pulsante riga o doppio click). */
function openEdit(row: IObjects, _api?: PachiTable2Api<IObjects>): void {
  void router.push(`/objects/${row.id}`)
}

/** Apre il dialog di creazione: con «Tutte le zone» chiede prima la zona di destinazione. */
function openCreate(api: PachiTable2Api<IObjects>): void {
  if (selectedZoneId.value !== ALL_ZONES) {
    void openDialog(api, selectedZoneId.value)
    return
  }
  $q.dialog({ component: ZonePickDialog, componentProps: { zones: zones.value } }).onOk((zoneId: number) => {
    void openDialog(api, zoneId)
  })
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
  }).onOk(() => {
    // gli errori (es. 409 in uso nei reset) li mostra già il dialog globale dell'HTTP client
    api.deleteRecord(row).catch(() => undefined)
  })
}

onMounted(loadLookups)
</script>
