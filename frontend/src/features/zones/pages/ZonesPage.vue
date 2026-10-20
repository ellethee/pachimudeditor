<template>
  <div class="q-pa-md">
    <pachi-table2
      ref="table"
      url="/api/zones"
      :columns="columns"
      :initial-sort="[{ column: 'vnum', direction: 'asc' }]"
      use-col-actions="emit-delete"
      :can-edit="canActOnRow"
      :can-delete="canDeleteRow"
      error-banner
      dense
      :rez-offset="REZ_OFFSET"
      @pt2:edit-item="onEdit"
      @pt2:delete-item="onDelete"
    >
      <template #error="{ error, retry }">
        <table-error :error="error" :retry="retry" />
      </template>
      <template #toolbar-actions="{ api }">
        <q-btn v-if="!readOnly" color="primary" :icon="mdiPlus" :label="t('zones.create')" no-caps @click="openCreate(api)" />
        <q-btn flat round :icon="mdiRefresh" :aria-label="t('zones.reload')" @click="api.reload()" />
      </template>

      <template #body-cell-enabled="{ slotProps }">
        <q-td :props="slotProps">
          <q-icon
            :name="slotProps.row.enabled ? mdiCheckCircle : mdiCloseCircle"
            :color="slotProps.row.enabled ? 'positive' : 'grey'"
            size="sm"
          />
        </q-td>
      </template>

      <template #body-cell-extra="{ slotProps, api }">
        <q-td :props="slotProps">
          <q-btn v-if="supports('supportsResetScripts') && !guardOf(slotProps.row.extra).corrupted" dense flat round :icon="mdiReplay" @click="openResets(slotProps.row)" :aria-label="t('zones.actions.resets')">
            <q-tooltip>{{ t('zones.actions.resets') }}</q-tooltip>
          </q-btn>
          <q-btn v-if="!readOnly && !guardOf(slotProps.row.extra).corrupted" dense flat round :icon="mdiContentCopy" @click="openClone(slotProps.row, api)" :aria-label="t('zones.actions.clone')">
            <q-tooltip>{{ t('zones.actions.clone') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { QTableColumn } from 'quasar'
import { mdiCheckCircle, mdiCloseCircle, mdiContentCopy, mdiPlus, mdiRefresh, mdiReplay } from '@quasar/extras/mdi-v7'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import type { PachiTable2Api, PachiTable2Exposed } from '@ilpachi/pachi-kit/table'
import { useZoneDialogs } from '../composables/use-zone-dialogs'
import { getZone } from '../services/zones-api'
import { useWorld } from '../../shared/helpers/world-state'
import { guardOf } from '../../shared/helpers/record-guard'
import { whenReady } from '../../shared/helpers/when-ready'
import type { IZone } from '../types/zones'
import TableError from '../../shared/components/TableError.vue'

/** Spazio (px) lasciato sotto la tabella. */
const REZ_OFFSET = 16

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const { readOnly, supports, fieldOf } = useWorld()
const table = ref<PachiTable2Exposed<IZone> | null>(null)
const { openCreate, openEdit, openClone, deleteZone } = useZoneDialogs()

/** Colonne della tabella: `name` è anche la chiave di ordinamento inviata al backend (`orderBy`). */
const columns = computed<QTableColumn<IZone>[]>(() => [
  { name: 'vnum', label: t('zones.columns.vnum'), field: 'vnum', align: 'left', sortable: true },
  { name: 'name', label: t('zones.columns.name'), field: 'name', align: 'left', sortable: true },
  { name: 'range', label: t('zones.columns.range'), field: rangeOf, align: 'left' },
  { name: 'builder', label: t('zones.columns.builder'), field: 'builder', align: 'left', sortable: true },
  {
    name: 'levels',
    label: t('zones.columns.levels'),
    field: (row: IZone) => `${row.minLevel}-${row.maxLevel}`,
    align: 'left',
  },
  { name: 'lifespanMinutes', label: t('zones.columns.lifespan'), field: 'lifespanMinutes', align: 'left', sortable: true },
  { name: 'enabled', label: t('zones.columns.enabled'), field: 'enabled', align: 'center', sortable: true },
  { name: 'extra', label: '', field: 'id', align: 'right' },
])

/**
 * Range di vnum della zona; `0-0` in un mondo che lo deriva (bottomVnum di sola lettura) significa che la zona
 * non possiede vnum.
 *
 * @param row - zona
 */
function rangeOf(row: IZone): string {
  if (row.bottomVnum === 0 && row.topVnum === 0 && fieldOf('zone', 'bottomVnum')?.readOnly === true) return t('worlds.noRange')
  return `${row.bottomVnum}-${row.topVnum}`
}

/** Tutte le righe sono modificabili/eliminabili (tipizza anche la riga `T` della tabella). */
function canActOnRow(_row: IZone): boolean {
  return true
}

/** Eliminabili solo in un mondo scrivibile. */
function canDeleteRow(row: IZone): boolean {
  return !readOnly.value && !guardOf(row.extra).corrupted
}

/** Deep-link `?zoneId=`: apre l'editor della zona (poi toglie il parametro, così un ricaricamento non lo riapre). */
async function openFromQuery(): Promise<void> {
  const id = Number(route.query.zoneId)
  if (route.query.zoneId === undefined || !Number.isFinite(id)) return
  try {
    const zone = await getZone(id)
    await router.replace({ path: route.path })
    const api = await whenReady(() => table.value?.api)
    await openEdit(zone, api)
  } catch {
    // zona inesistente o non leggibile: resta l'elenco
  }
}

onMounted(openFromQuery)

/** Apre l'editor dello script di reset della zona. */
function openResets(zone: IZone): void {
  void router.push(`/zones/${zone.id}/resets`)
}

/** Modifica una zona dal pulsante di riga. */
function onEdit(row: IZone, api: PachiTable2Api<IZone>): void {
  void openEdit(row, api)
}

/** Elimina una zona dopo conferma dal pulsante di riga. */
function onDelete(row: IZone, api: PachiTable2Api<IZone>): void {
  void deleteZone(row, api)
}
</script>

