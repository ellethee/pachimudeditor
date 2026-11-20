<template>
  <div class="column no-wrap q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <h1 class="text-h5 q-ma-none">{{ t('rooms.title') }}</h1>
      <q-select
        v-model="selectedZoneId"
        :options="zoneOptions"
        option-value="id"
        option-label="label"
        emit-value
        map-options
        :label="t('rooms.zone')"
        style="min-width: 260px"
        dense
        outlined
      />
      <q-space />
      <q-btn
        flat
        :icon="mdiGraphOutline"
        :label="t('rooms.openMap')"
        :to="{ path: '/rooms/map', query: mapZoneId === null ? {} : { zoneId: String(mapZoneId) } }"
      />
    </div>

    <list-filters v-if="ready && !loadError" v-model="filters" :controls="controls" />
    <pachi-loading-state v-if="loading" :label="t('rooms.loading')" />
    <pachi-error-state
      v-else-if="loadError"
      :title="t('rooms.errorTitle')"
      :description="t('rooms.errorDescription')"
      :primary-label="t('rooms.retry')"
      @primary="init"
    />
    <pachi-empty-state
      v-else-if="store.zones.length === 0"
      :icon="mdiInbox"
      :title="t('rooms.noZoneTitle')"
      :description="t('rooms.noZoneDescription')"
    />
    <pachi-table2
      v-else-if="ready"
      ref="table"
      url="/api/rooms"
      :columns="columns"
      :extra-params="extraParams"
      :initial-sort="[]"
      use-col-actions="emit-delete"
      :can-edit="canRow"
      :can-delete="canDelete"
      error-banner
      :rez-offset="16"
      dense
      @pt2:edit-item="onEdit"
      @pt2:delete-item="onDelete"
      @row-dblclick="onRowDblClick"
    >
      <template #error="{ error, retry }">
        <table-error :error="error" :retry="retry" />
      </template>
      <template #toolbar-actions="{ api }">
        <columns-menu :names="columnNames" :model-value="visibleColumns" :label-of="columnLabel" @toggle="toggleColumn" @reset="resetColumns" />
        <q-btn v-if="!readOnly" color="primary" :icon="mdiPlus" :label="t('rooms.create')" @click="onCreate" />
        <q-btn flat round :icon="mdiRefresh" :aria-label="t('rooms.reload')" @click="api.reload()" />
      </template>

      <template #body-cell-clone="{ slotProps }">
        <q-td :props="slotProps">
          <q-btn v-if="!readOnly" dense flat round :icon="mdiContentCopy" @click.stop="dialogs.openClone(slotProps.row)" :aria-label="t('rooms.clone.action')">
            <q-tooltip>{{ t('rooms.clone.action') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { QTableColumn } from 'quasar'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { mdiContentCopy, mdiGraphOutline, mdiInbox, mdiPlus, mdiRefresh } from '@quasar/extras/mdi-v7'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import type { PachiTable2Api, PachiTable2Exposed } from '@ilpachi/pachi-kit/table'
import { PachiEmptyState, PachiErrorState, PachiLoadingState } from '@ilpachi/pachifastquasar'
import { useRoomDialogs } from '../composables/use-room-dialogs'
import { getRoomUsage } from '../services/rooms-api'
import { useRoomsStore } from '../stores/use-rooms-store'
import { useWorld } from '../../shared/helpers/world-state'
import type { IRoom } from '../types/rooms'
import TableError from '../../shared/components/TableError.vue'
import ColumnsMenu from '../../shared/components/ColumnsMenu.vue'
import ListFilters from '../../shared/components/ListFilters.vue'
import ZonePickDialog from '../../shared/components/ZonePickDialog.vue'
import { enumNames } from '../../shared/helpers/descriptor-rows'
import {
  emptyFilters,
  filterQueryKeys,
  filtersFromQuery,
  filtersToParams,
  loadColumns,
  saveColumns,
  summarize,
} from '../../shared/helpers/list-filters'
import type { IFilterControl, IListFilters } from '../../shared/helpers/list-filters'
import { COLUMNS_KEY, COLUMN_NAMES, FILTER_SPECS, defaultColumns } from '../utils/list-query'

/**
 * Lista delle stanze di una zona (pachi-table2 lato server) con editor (uscite ed extra
 * description) e clonazione. Query string: `zoneId` seleziona la zona, `roomId` apre l'editor
 * (usata dalla mappa).
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useRoomsStore()
const $q = useQuasar()
const { readOnly, fieldOf } = useWorld()

const table = ref<PachiTable2Exposed<IRoom> | null>(null)
const loading = ref(true)
const loadError = ref(false)

const dialogs = useRoomDialogs(() => table.value?.reload())

/** Valore del selettore di zona per «tutte le zone» (gli id reali sono >= 0). */
const ALL_ZONES = -1
const selectedZoneId = ref<number>(ALL_ZONES)
/** `true` a lookup caricati: la tabella può partire con zona e filtri letti dall'URL. */
const ready = ref(false)
const filters = ref<IListFilters>(emptyFilters(FILTER_SPECS))

/** Opzioni del selettore: «Tutte le zone» e poi le zone. */
const zoneOptions = computed(() => [
  { id: ALL_ZONES, label: t('rooms.allZones') },
  ...store.zones.map((zone) => ({ id: zone.id, label: `${zone.vnum} - ${zone.name}` })),
])
/** Zona da aprire nella mappa (che ne richiede una): quella scelta, altrimenti l'ultima zona usata. */
const mapZoneId = computed<number | null>(() => (selectedZoneId.value !== ALL_ZONES ? selectedZoneId.value : store.selectedZoneId))

/** Filtro per zona (se scelta) e filtri sulle statistiche inviati alla tabella. */
const extraParams = computed<Record<string, unknown>>(() => ({
  ...(selectedZoneId.value !== ALL_ZONES ? { zoneId: selectedZoneId.value } : {}),
  ...filtersToParams(FILTER_SPECS, filters.value),
}))

/** `true` se il mondo ha il campo della stanza (un campo `unsupported` non ha colonna né filtro). */
function hasField(name: string): boolean {
  return !fieldOf('room', name)?.unsupported
}

/** Controlli della barra dei filtri (testi, opzioni e campi non supportati nascosti). */
const controls = computed<IFilterControl[]>(() =>
  FILTER_SPECS.map((spec): IFilterControl => {
    const base = { ...spec, label: columnLabel(spec.key), hidden: !hasField(spec.key) }
    if (spec.key === 'sectorType') return { ...base, options: (store.enums?.sectorType ?? []).map((o) => ({ value: o.value, label: o.label })) }
    if (spec.key === 'flags') {
      const names = enumNames(store.enums as unknown as Record<string, unknown> | undefined, fieldOf('room', 'flags'))
      return { ...base, free: true, options: names.map((n) => ({ value: n, label: n })) }
    }
    if (spec.key === 'clanId') return { ...base, free: true }
    return base
  }),
)

/** Colonne selezionabili in questo mondo (senza quelle dei campi che non ha). */
const columnNames = computed<string[]>(() => COLUMN_NAMES.filter((name) => hasField(name)))
/** Colonne visibili: scelta salvata dal viewer, altrimenti pochi default (telefono) o i principali. */
const visibleColumns = ref<string[]>(loadColumns(COLUMNS_KEY, COLUMN_NAMES) ?? defaultColumns($q.screen.lt.sm))

/**
 * Mostra o nasconde una colonna e salva la scelta.
 *
 * @param name - nome della colonna
 * @param on - `true` per mostrarla
 */
function toggleColumn(name: string, on: boolean): void {
  visibleColumns.value = COLUMN_NAMES.filter((column) => (column === name ? on : visibleColumns.value.includes(column)))
  saveColumns(COLUMNS_KEY, visibleColumns.value)
}

/** Ripristina le colonne di default. */
function resetColumns(): void {
  visibleColumns.value = defaultColumns($q.screen.lt.sm)
  saveColumns(COLUMNS_KEY, visibleColumns.value)
}

/**
 * Intestazione di una colonna (e etichetta del filtro corrispondente).
 *
 * @param name - nome della colonna
 */
function columnLabel(name: string): string {
  return t(`rooms.columns.${name}`)
}

/** Etichetta del terreno dal valore numerico. */
function sectorLabel(value: number): string {
  return store.enums?.sectorType.find((option) => option.value === value)?.label ?? String(value)
}

/**
 * Nome della zona.
 *
 * @param zoneId - id della zona
 */
function zoneName(zoneId: number): string {
  return store.zones.find((zone) => zone.id === zoneId)?.name ?? String(zoneId)
}

/** Tutte le colonne (il `name` è la chiave di `orderBy` del backend); mostrate solo quelle scelte e supportate, poi la clonazione. */
const allColumns = computed<QTableColumn<IRoom>[]>(() => {
  const num = (name: 'healRate' | 'manaRate'): QTableColumn<IRoom> => ({
    name,
    label: columnLabel(name),
    field: name,
    align: 'right',
    sortable: true,
  })
  return [
    { name: 'vnum', label: columnLabel('vnum'), field: 'vnum', align: 'left', sortable: true },
    { name: 'name', label: columnLabel('name'), field: 'name', align: 'left', sortable: true },
    { name: 'zoneId', label: columnLabel('zoneId'), field: (row) => zoneName(row.zoneId), align: 'left', sortable: true },
    { name: 'sectorType', label: columnLabel('sectorType'), field: (row) => sectorLabel(row.sectorType), align: 'left', sortable: true },
    {
      name: 'flags',
      label: columnLabel('flags'),
      field: (row) => summarize(row.flags),
      align: 'left',
      style: 'max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap',
    },
    num('healRate'),
    num('manaRate'),
    { name: 'clanId', label: columnLabel('clanId'), field: (row) => row.clanId ?? '', align: 'left', sortable: true },
    { name: 'owner', label: columnLabel('owner'), field: (row) => row.owner ?? '', align: 'left', sortable: true },
  ]
})
const columns = computed<QTableColumn<IRoom>[]>(() => [
  ...allColumns.value.filter((column) => visibleColumns.value.includes(column.name) && columnNames.value.includes(column.name)),
  { name: 'clone', label: '', field: 'id', align: 'right', sortable: false },
])

/** Abilitazione dei pulsanti di riga (sempre; tipizza la riga per l'inferenza di `PachiTable2`). */
function canRow(_row: IRoom): boolean {
  return true
}

/** Eliminabili solo in un mondo scrivibile. */
function canDelete(_row: IRoom): boolean {
  return !readOnly.value
}

/** Crea una stanza: con «Tutte le zone» chiede prima la zona di destinazione. */
function onCreate(): void {
  if (selectedZoneId.value !== ALL_ZONES) {
    void dialogs.openCreate(selectedZoneId.value)
    return
  }
  $q.dialog({ component: ZonePickDialog, componentProps: { zones: store.zones.map((z) => ({ id: z.id, name: `${z.vnum} - ${z.name}` })), scope: 'rooms' } }).onOk(
    (zoneId: number) => {
      void dialogs.openCreate(zoneId)
    },
  )
}

/** Apre il dettaglio della stanza (pulsante di riga). */
async function onEdit(row: IRoom): Promise<void> {
  await router.push(`/rooms/${row.id}`)
}

/** Doppio clic su una riga: apre il dettaglio. */
async function onRowDblClick(_event: Event, row: IRoom): Promise<void> {
  await router.push(`/rooms/${row.id}`)
}

/**
 * Eliminazione con avviso se la stanza è usata dai reset (il backend rifiuterà finché non si aggiornano).
 *
 * @param row - stanza da eliminare
 * @param api - API esposta dalla tabella
 */
async function onDelete(row: IRoom, api: PachiTable2Api<IRoom>): Promise<void> {
  const usage = await getRoomUsage(row.id)
  const warning =
    usage.length > 0
      ? ' ' +
        t('rooms.delete.usageWarning', {
          count: usage.length,
          zones: [...new Set(usage.map((item) => item.zoneName))].join(', '),
        })
      : ''
  await api.confirmAction(t('rooms.delete.message', { name: row.name, vnum: row.vnum }) + warning, () =>
    api.deleteRecord(row),
  )
}

/** Carica zone ed enum; applica `zoneId`/`roomId` della query string. */
async function init(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    await Promise.all([store.ensureEnums(), store.loadZones()])
    applyQuery()
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
  ready.value = !loadError.value
  const queryRoomId = Number(route.query.roomId)
  if (!loadError.value && Number.isFinite(queryRoomId) && queryRoomId > 0) {
    // deep-link `?roomId=`: apre il dettaglio della stanza
    await router.replace(`/rooms/${queryRoomId}`)
  }
}

/** Zona e filtri dall'URL (zona sconosciuta o assente: tutte le zone). */
function applyQuery(): void {
  const wanted = route.query.zoneId === undefined ? NaN : Number(route.query.zoneId)
  selectedZoneId.value = store.zones.find((zone) => zone.id === wanted)?.id ?? ALL_ZONES
  filters.value = filtersFromQuery(FILTER_SPECS, route.query)
}

/** Query string corrispondente allo stato (zona e filtri) mantenendo gli altri parametri dell'URL. */
function stateQuery(): Record<string, string> {
  const owned = filterQueryKeys(FILTER_SPECS)
  const base = Object.fromEntries(Object.entries(route.query).filter(([key]) => key !== 'zoneId' && !owned.includes(key))) as Record<
    string,
    string
  >
  const zone = selectedZoneId.value !== ALL_ZONES ? { zoneId: String(selectedZoneId.value) } : {}
  const entries = Object.entries(filtersToParams(FILTER_SPECS, filters.value, true)).map(([key, value]) => [key, String(value)])
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
// la mappa e i dialog seguono l'ultima zona scelta nella lista
watch(selectedZoneId, (id) => {
  if (id !== ALL_ZONES) store.selectedZoneId = id
})
// navigazione indietro/avanti o link condiviso: lo stato segue l'URL
watch(
  () => route.query,
  () => {
    if (!ready.value) return
    const parsed = filtersFromQuery(FILTER_SPECS, route.query)
    const zone = Number(route.query.zoneId)
    const nextZone = store.zones.some((z) => z.id === zone) ? zone : ALL_ZONES
    if (nextZone === selectedZoneId.value && JSON.stringify(parsed) === JSON.stringify(filters.value)) return
    applyQuery()
  },
)

onMounted(init)
</script>
