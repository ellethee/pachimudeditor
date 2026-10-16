<template>
  <div>
    <div class="row items-center q-gutter-md q-mb-sm">
      <q-select
        v-model="accountFilter"
        :options="accounts"
        option-value="id"
        option-label="username"
        emit-value
        map-options
        clearable
        dense
        outlined
        style="min-width: 240px"
        :label="t('players.characters.filterAccount')"
      />
    </div>
    <pachi-error-state
      v-if="loadError"
      :title="t('players.errorTitle')"
      :description="t('players.errorDescription')"
      :primary-label="t('players.retry')"
      @primary="loadLookups"
    />
    <pachi-table2
      v-else-if="lookups"
      ref="table"
      :url="CHARACTERS_URL"
      :columns="columns"
      :extra-params="extraParams"
      :initial-sort="[{ column: 'name', direction: 'asc' }]"
      :can-edit="allowRow"
      error-banner
      dense
      @row-dblclick="(_evt: Event, row: ICharacter) => openEdit(row)"
    >
      <template #toolbar-actions="{ api }">
        <q-btn flat round :icon="mdiRefresh" :aria-label="t('players.reload')" @click="api.reload()" />
      </template>
      <template #body-cell-actions="{ slotProps, api }">
        <q-td :props="slotProps" auto-width>
          <q-btn flat round dense :icon="mdiPencil" :aria-label="t('players.edit')" @click="openEdit(slotProps.row, api)">
            <q-tooltip>{{ t('players.edit') }}</q-tooltip>
          </q-btn>
          <q-btn flat round dense :icon="mdiMapMarkerRadius" :aria-label="t('players.characters.teleport')" @click="teleport(slotProps.row, api)">
            <q-tooltip>{{ t('players.characters.teleport') }}</q-tooltip>
          </q-btn>
          <q-btn flat round dense :icon="mdiBagPersonal" :aria-label="t('players.inventory.open')" @click="openInventory(slotProps.row)">
            <q-tooltip>{{ t('players.inventory.open') }}</q-tooltip>
          </q-btn>
          <q-btn flat round dense :icon="mdiDelete" :aria-label="t('players.delete')" @click="confirmDelete(slotProps.row, api)">
            <q-tooltip>{{ t('players.delete') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiBagPersonal, mdiDelete, mdiMapMarkerRadius, mdiPencil, mdiRefresh } from '@quasar/extras/mdi-v7'
import { PachiErrorState } from '@ilpachi/pachifastquasar'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import type { PachiTable2Api, PachiTable2Exposed } from '@ilpachi/pachi-kit/table'
import { PachiEditDialog } from '@ilpachi/pachi-kit/edit-dialog'
import type { AwaitableData, ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import { describeError } from '../helpers/describe-error'
import { buildIdentityRows, buildListRows, buildStateRows, buildStatsRows } from '../helpers/character-rows'
import { localizeLookups } from '../helpers/labels'
import {
  CHARACTERS_URL,
  deleteCharacter,
  getCharacter,
  getLookups,
  listAllAccounts,
  searchRooms,
  teleportCharacter,
  updateCharacter,
} from '../services/players-api'
import type { IAccount, ICharacter, ICharacterDetail, ICharacterPatch, IPlayerLookups, IRoomRef } from '../types/players'
import InventoryDialog from './InventoryDialog.vue'
import PickerDialog from './PickerDialog.vue'

const props = defineProps<{
  /** Account su cui filtrare (impostato dal tab account). */
  accountId?: number | undefined
}>()

const { t, d } = useI18n()
const $q = useQuasar()
const table = ref<PachiTable2Exposed<ICharacter> | null>(null)

/** Serve a tipizzare la tabella su `ICharacter` (le azioni di riga sono personalizzate). */
const allowRow = (_row: ICharacter): boolean => true
const lookups = ref<IPlayerLookups>()
const accounts = ref<IAccount[]>([])
const loadError = ref(false)
const accountFilter = ref<number | null>(props.accountId ?? null)

watch(
  () => props.accountId,
  (value) => (accountFilter.value = value ?? null),
)

/** Filtro esatto per account inviato alla tabella. */
const extraParams = computed<Record<string, unknown>>(() =>
  accountFilter.value !== null ? { accountId: accountFilter.value } : {},
)

const columns = computed<QTableColumn<ICharacter>[]>(() => [
  { name: 'name', label: t('players.characters.name'), field: 'name', align: 'left', sortable: true },
  { name: 'accountId', label: t('players.characters.account'), field: (r: ICharacter) => r.accountUsername ?? r.accountId, align: 'left', sortable: true },
  { name: 'level', label: t('players.characters.level'), field: 'level', align: 'right', sortable: true },
  { name: 'classId', label: t('players.characters.class'), field: 'classId', align: 'left' },
  { name: 'raceId', label: t('players.characters.race'), field: 'raceId', align: 'left' },
  {
    name: 'room',
    label: t('players.characters.room'),
    field: (r: ICharacter) => (r.currentRoomId === null ? '—' : `${r.currentRoomVnum} - ${r.currentRoomName}`),
    align: 'left',
  },
  {
    name: 'lastPlayedAt',
    label: t('players.characters.lastPlayedAt'),
    field: (r: ICharacter) => (r.lastPlayedAt ? d(new Date(r.lastPlayedAt), 'short') : '—'),
    align: 'left',
    sortable: true,
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
])

/** Carica lookup (sesso, posizione, razze, classi) e account per le select. */
async function loadLookups(): Promise<void> {
  loadError.value = false
  try {
    const [lk, acc] = await Promise.all([getLookups(), listAllAccounts()])
    lookups.value = localizeLookups(lk)
    accounts.value = acc
  } catch {
    loadError.value = true
  }
}

/**
 * Esegue un'azione e ricarica; gli errori diventano una notifica.
 *
 * @param action - chiamata al backend
 * @param api - API della tabella
 */
async function run(action: () => Promise<unknown>, api: PachiTable2Api<ICharacter>): Promise<void> {
  try {
    await action()
    await api.reload()
  } catch (e) {
    $q.notify({ type: 'negative', message: await describeError(e) })
  }
}

/**
 * Apre il form di modifica con la scheda completa del personaggio.
 *
 * @param row - riga della tabella
 * @param api - API della tabella (opzionale: si usa quella della ref)
 */
async function openEdit(row: ICharacter, api?: PachiTable2Api<ICharacter>): Promise<void> {
  const tableApi = api ?? table.value?.api
  const lk = lookups.value
  if (!tableApi || !lk) return
  let detail: ICharacterDetail
  try {
    detail = await getCharacter(row.id)
  } catch (e) {
    $q.notify({ type: 'negative', message: await describeError(e) })
    return
  }
  const initial: Record<string, unknown> = { ...detail }
  const section = (key: string, props: Record<string, unknown>, order: number, opened: boolean): ISectionDefinition => ({
    key,
    title: t(`players.sections.${key}`),
    component: markRaw(FieldsSection),
    props,
    initialValue: initial,
    order,
    container: { type: 'expansion', title: t(`players.sections.${key}`), defaultOpened: opened },
  })
  const sections: ISectionDefinition[] = [
    section('identity', { rows: buildIdentityRows(t, lk, accounts.value) }, 10, true),
    section('state', { rows: buildStateRows(t, lk) }, 20, true),
    section('stats', { rows: buildStatsRows(t) }, 30, false),
    section('lists', { rows: buildListRows(t) }, 40, false),
  ]
  $q.dialog({
    component: PachiEditDialog,
    componentProps: {
      title: t('players.characters.editTitle', { name: detail.name }),
      icon: mdiPencil,
      sections,
      avoidHideWithChanges: true,
      width: '760px',
      maxWidth: '95vw',
    },
  }).onOk(async ({ data, onSuccess, onError }: AwaitableData) => {
    const patch = Object.assign({}, ...Object.values(data.sections)) as ICharacterPatch
    try {
      await updateCharacter(detail.id, patch)
      await tableApi.reload()
      onSuccess()
    } catch (e) {
      onError(new Error(await describeError(e)))
    }
  })
}

/**
 * Selettore di stanza e teletrasporto.
 *
 * @param row - personaggio
 * @param api - API della tabella
 */
function teleport(row: ICharacter, api: PachiTable2Api<ICharacter>): void {
  $q.dialog({
    component: PickerDialog,
    componentProps: {
      title: t('players.characters.teleportTitle', { name: row.name }),
      label: t('players.characters.pickRoom'),
      confirmLabel: t('players.characters.teleport'),
      search: searchRooms,
      optionLabel: (r: IRoomRef) => `${r.vnum} - ${r.name}`,
    },
  }).onOk((roomId: number) => void run(() => teleportCharacter(row.id, roomId), api))
}

/**
 * Apre l'inventario.
 *
 * @param row - personaggio
 */
function openInventory(row: ICharacter): void {
  $q.dialog({ component: InventoryDialog, componentProps: { characterId: row.id, characterName: row.name } })
}

/**
 * Conferma ed elimina (con scelta cascata sull'inventario).
 *
 * @param row - personaggio
 * @param api - API della tabella
 */
function confirmDelete(row: ICharacter, api: PachiTable2Api<ICharacter>): void {
  $q.dialog({
    title: t('players.characters.deleteTitle'),
    message: t('players.characters.deleteMessage', { name: row.name }),
    options: { type: 'toggle', model: [], items: [{ label: t('players.characters.cascade'), value: 'cascade' }] },
    cancel: true,
    persistent: true,
  }).onOk((choice: string[]) =>
    void run(() => deleteCharacter(row.id, Array.isArray(choice) && choice.includes('cascade')), api),
  )
}

onMounted(loadLookups)
</script>
