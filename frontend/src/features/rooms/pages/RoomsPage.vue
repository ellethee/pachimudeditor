<template>
  <div class="column no-wrap q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <h1 class="text-h5 q-ma-none">{{ t('rooms.title') }}</h1>
      <q-select
        v-model="store.selectedZoneId"
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
        :to="{ path: '/rooms/map', query: store.selectedZoneId === null ? {} : { zoneId: String(store.selectedZoneId) } }"
      />
    </div>

    <pachi-loading-state v-if="loading" :label="t('rooms.loading')" />
    <pachi-error-state
      v-else-if="loadError"
      :title="t('rooms.errorTitle')"
      :description="t('rooms.errorDescription')"
      :primary-label="t('rooms.retry')"
      @primary="init"
    />
    <pachi-empty-state
      v-else-if="store.selectedZoneId === null"
      :icon="mdiInbox"
      :title="t('rooms.noZoneTitle')"
      :description="t('rooms.noZoneDescription')"
    />
    <pachi-table2
      v-else
      ref="table"
      url="/api/rooms"
      :columns="columns"
      :extra-params="extraParams"
      :initial-sort="[{ column: 'vnum', direction: 'asc' }]"
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
import { computed, onMounted, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
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

/**
 * Lista delle stanze di una zona (pachi-table2 lato server) con editor (uscite ed extra
 * description) e clonazione. Query string: `zoneId` seleziona la zona, `roomId` apre l'editor
 * (usata dalla mappa).
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useRoomsStore()
const { readOnly } = useWorld()

const table = ref<PachiTable2Exposed<IRoom> | null>(null)
const loading = ref(true)
const loadError = ref(false)

const dialogs = useRoomDialogs(() => table.value?.reload())

const zoneOptions = computed(() =>
  store.zones.map((zone) => ({ id: zone.id, label: `${zone.vnum} - ${zone.name}` })),
)
const extraParams = computed<Record<string, unknown>>(() =>
  store.selectedZoneId !== null ? { zoneId: store.selectedZoneId } : {},
)

/** Etichetta del terreno dal valore numerico. */
function sectorLabel(value: number): string {
  return store.enums?.sectorType.find((option) => option.value === value)?.label ?? String(value)
}

const columns = computed<QTableColumn<IRoom>[]>(() => [
  { name: 'vnum', label: t('rooms.fields.vnum'), field: 'vnum', align: 'left', sortable: true },
  { name: 'name', label: t('rooms.fields.name'), field: 'name', align: 'left', sortable: true },
  {
    name: 'sectorType',
    label: t('rooms.fields.sectorType'),
    field: 'sectorType',
    align: 'left',
    sortable: true,
    format: (value: number) => sectorLabel(value),
  },
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

/** Crea una stanza nella zona selezionata. */
async function onCreate(): Promise<void> {
  if (store.selectedZoneId !== null) await dialogs.openCreate(store.selectedZoneId)
}

/** Modifica una stanza (pulsante di riga). */
async function onEdit(row: IRoom): Promise<void> {
  await dialogs.openEdit(row.id)
}

/** Doppio clic su una riga: apre l'editor. */
async function onRowDblClick(_event: Event, row: IRoom): Promise<void> {
  await dialogs.openEdit(row.id)
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
    const queryZoneId = Number(route.query.zoneId)
    if (Number.isFinite(queryZoneId) && store.zones.some((zone) => zone.id === queryZoneId)) {
      store.selectedZoneId = queryZoneId
    }
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
  const queryRoomId = Number(route.query.roomId)
  if (!loadError.value && Number.isFinite(queryRoomId) && queryRoomId > 0) {
    // evita di riaprire l'editor a ogni ricarica della pagina
    await router.replace({ path: '/rooms', query: { zoneId: route.query.zoneId } })
    await dialogs.openEdit(queryRoomId)
  }
}

onMounted(init)
</script>
