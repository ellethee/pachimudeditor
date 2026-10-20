<template>
  <div>
    <div v-if="!prototype" class="row items-center q-col-gutter-md q-mb-md">
      <div class="col-12 col-sm-4 col-md-3">
        <q-select
          v-model="filterZoneId"
          :options="zones"
          option-value="id"
          option-label="name"
          emit-value
          map-options
          clearable
          :label="t('instances.filters.zone')"
          outlined
          dense
        />
      </div>
      <div class="col-12 col-sm-4 col-md-3">
        <q-input
          v-model.number="filterVnum"
          type="number"
          clearable
          :label="t('instances.filters.prototypeVnum')"
          outlined
          dense
        />
      </div>
      <div class="col-12 col-sm-4 col-md-4">
        <room-picker v-model="filterRoomId" :label="t('instances.filters.room')" clearable />
      </div>
    </div>

    <pachi-table2
      ref="table"
      :url="instancesUrl(kind)"
      :columns="columns"
      :extra-params="extraParams"
      :initial-sort="[{ column: 'id', direction: 'desc' }]"
      use-col-actions="emit-delete"
      :can-edit="allowRow"
      :can-delete="allowRow"
      error-banner
      dense
      @pt2:edit-item="openEdit"
      @pt2:delete-item="confirmDelete"
      @row-dblclick="(_evt: Event, row: Row) => openEdit(row)"
    >
      <template #error="{ error, retry }">
        <table-error :error="error" :retry="retry" />
      </template>
      <template #toolbar-actions="{ api }">
        <q-btn color="primary" :icon="mdiPlus" :label="t(`instances.${kind}.new`)" :disable="readOnly" @click="openCreate(api)" />
        <q-btn flat round :icon="mdiRefresh" :aria-label="t('instances.reload')" @click="api.reload()" />
      </template>
      <template #body-cell-prototype="{ slotProps }">
        <q-td :props="slotProps">
          <router-link :to="{ path: kind === 'mob' ? '/mobs' : '/objects', query: { zoneId: slotProps.row.prototypeZoneId } }">
            {{ slotProps.row.prototypeVnum }} — {{ slotProps.row.prototypeName }}
          </router-link>
        </q-td>
      </template>
      <template #body-cell-room="{ slotProps }">
        <q-td :props="slotProps">
          <router-link
            v-if="slotProps.row.roomId"
            :to="{ path: '/rooms', query: { zoneId: slotProps.row.zoneId, roomId: slotProps.row.roomId } }"
          >
            {{ slotProps.row.roomVnum }} — {{ slotProps.row.roomName }}
          </router-link>
          <span v-else>—</span>
        </q-td>
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
/**
 * Tabella di istanze vive (mob o oggetti) con filtri, creazione, modifica e despawn.
 *
 * Con `prototype` elenca solo le istanze di quel prototipo (senza filtri e senza colonna prototipo) e
 * nuove istanze si generano da quel prototipo: è la base di `InstancesTab`.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiPlus, mdiRefresh } from '@quasar/extras/mdi-v7'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import type { PachiTable2Api, PachiTable2Exposed } from '@ilpachi/pachi-kit/table'
import RoomPicker from './RoomPicker.vue'
import MobInstanceDialog from './MobInstanceDialog.vue'
import ObjectInstanceDialog from './ObjectInstanceDialog.vue'
import { describeError } from '../helpers/describe-error'
import { useWorld } from '../../shared/helpers/world-state'
import { enumLabel } from '../../shared/helpers/enum-labels'
import { deleteInstance, instancesUrl, listZones } from '../services/instances-api'
import TableError from '../../shared/components/TableError.vue'
import type {
  ContentsPolicy,
  IMobInstance,
  IObjectInstance,
  IPrototypeRef,
  IZoneRef,
  InstanceKind,
} from '../types/instances'

type Row = IMobInstance | IObjectInstance

const props = defineProps<{
  /** Mob o oggetti. */
  kind: InstanceKind
  /** Se presente, elenca solo le istanze di questo prototipo. */
  prototype?: IPrototypeRef
}>()

const { t } = useI18n()
const $q = useQuasar()
const { readOnly } = useWorld()

const table = ref<PachiTable2Exposed<Row> | null>(null)
const zones = ref<IZoneRef[]>([])
const filterZoneId = ref<number | null>(null)
const filterVnum = ref<number | null>(null)
const filterRoomId = ref<number | null>(null)

/** Righe modificabili/eliminabili solo in un mondo scrivibile (serve anche a tipizzare la tabella). */
const allowRow = (_row: Row): boolean => !readOnly.value

/** Filtri esatti inviati alla tabella (solo quelli valorizzati). */
const extraParams = computed<Record<string, unknown>>(() => {
  if (props.prototype) return { prototypeId: props.prototype.id }
  const params: Record<string, unknown> = {}
  if (filterZoneId.value !== null) params.zoneId = filterZoneId.value
  if (filterVnum.value !== null && String(filterVnum.value) !== '') params.prototypeVnum = filterVnum.value
  if (filterRoomId.value !== null) params.roomId = filterRoomId.value
  return params
})

/**
 * Testo della posizione di un oggetto (tipo + bersaglio).
 *
 * @param row - oggetto vivo
 */
function locationText(row: IObjectInstance): string {
  const kind = t(`instances.locationKinds.${row.locationKind}`)
  if (row.locationKind === 'room') return `${kind} ${row.roomVnum ?? row.locationId}`
  const slot = row.equippedSlot ? ` (${row.equippedSlot})` : ''
  return `${kind} #${row.locationId}${slot}`
}

const columns = computed<QTableColumn<Row>[]>(() => {
  const cols: QTableColumn<Row>[] = [
    { name: 'id', label: t('instances.columns.id'), field: 'id', align: 'left', sortable: true },
  ]
  if (!props.prototype) {
    cols.push({
      name: 'prototype',
      label: t('instances.columns.prototype'),
      field: 'prototypeName',
      align: 'left',
      sortable: true,
    })
  }
  if (props.kind === 'mob') {
    cols.push(
      { name: 'room', label: t('instances.columns.room'), field: 'roomName', align: 'left' },
      { name: 'zoneName', label: t('instances.columns.zone'), field: 'zoneName', align: 'left', sortable: true },
      {
        name: 'hitPointsCurrent',
        label: t('instances.columns.hitPoints'),
        field: (row) => `${(row as IMobInstance).hitPointsCurrent} / ${(row as IMobInstance).hitPointsMax}`,
        align: 'left',
        sortable: true,
      },
      { name: 'gold', label: t('instances.columns.gold'), field: (row) => (row as IMobInstance).gold ?? '—', align: 'left', sortable: true },
      { name: 'itemCount', label: t('instances.columns.items'), field: (row) => (row as IMobInstance).itemCount, align: 'left' },
    )
  } else {
    cols.push(
      {
        name: 'objectType',
        label: t('instances.columns.type'),
        field: (row) =>
          enumLabel('objectType', { value: (row as IObjectInstance).objectType, label: String((row as IObjectInstance).objectType) }),
        align: 'left',
        sortable: true,
      },
      { name: 'location', label: t('instances.columns.location'), field: (row) => locationText(row as IObjectInstance), align: 'left' },
      { name: 'room', label: t('instances.columns.room'), field: 'roomName', align: 'left' },
      { name: 'charges', label: t('instances.columns.charges'), field: (row) => (row as IObjectInstance).charges ?? '—', align: 'left', sortable: true },
      { name: 'contentCount', label: t('instances.columns.contents'), field: (row) => (row as IObjectInstance).contentCount, align: 'left' },
    )
  }
  return cols
})

/** Apre il dialog di creazione/modifica del tipo giusto e ricarica la tabella a salvataggio avvenuto. */
function openDialog(api: PachiTable2Api<Row> | undefined, row?: Row): void {
  const component = props.kind === 'mob' ? MobInstanceDialog : ObjectInstanceDialog
  $q.dialog({
    component,
    componentProps: { instance: row, prototype: props.prototype },
  }).onOk(() => {
    void (api ?? table.value?.api)?.reload()
  })
}

/** Gestore dell'edit della tabella (pulsante riga o doppio click). */
function openEdit(row: Row, api?: PachiTable2Api<Row>): void {
  if (readOnly.value) return
  openDialog(api, row)
}

/** Apre il dialog di creazione. */
function openCreate(api: PachiTable2Api<Row>): void {
  openDialog(api)
}

/**
 * Chiede conferma (e, se ha contenuto, cosa farne) e fa il despawn dell'istanza.
 *
 * @param row - istanza da eliminare
 * @param api - API della tabella
 */
function confirmDelete(row: Row, api: PachiTable2Api<Row>): void {
  const hasContents = props.kind === 'mob' ? (row as IMobInstance).itemCount > 0 : (row as IObjectInstance).contentCount > 0
  const name = row.prototypeName
  $q.dialog({
    title: t('instances.delete.title'),
    message: t('instances.delete.message', { id: row.id, name }),
    cancel: true,
    ...(hasContents
      ? {
          options: {
            type: 'radio' as const,
            model: 'destroy',
            items: [
              { label: t(`instances.delete.${props.kind}.destroy`), value: 'destroy' },
              { label: t(`instances.delete.${props.kind}.drop`), value: 'drop' },
            ],
          },
        }
      : {}),
  }).onOk(async (choice?: ContentsPolicy) => {
    try {
      await deleteInstance(props.kind, row.id, hasContents ? (choice ?? 'destroy') : 'destroy')
      await api.reload()
    } catch (error) {
      $q.notify({ type: 'negative', message: await describeError(error) })
    }
  })
}

onMounted(async () => {
  if (props.prototype) return
  try {
    zones.value = await listZones()
  } catch {
    // il filtro per zona resta vuoto
  }
})

defineExpose({
  /** Ricarica la tabella. */
  reload: (): void => {
    void table.value?.api.reload()
  },
})
</script>
