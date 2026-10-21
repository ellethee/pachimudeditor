<template>
  <div class="q-pa-md" data-testid="player-files-page">
    <h1 class="text-h5 q-mt-none q-mb-md">{{ t('playerFiles.title') }}</h1>

    <q-banner
      v-if="info?.onlinePolicy === 'warn'"
      rounded
      class="bg-warning text-black q-mb-md"
      role="status"
      data-testid="players-warning"
    >
      <template #avatar><q-icon :name="mdiAlertOutline" /></template>
      <div>{{ t('playerFiles.warning') }}</div>
      <div v-if="status?.serverRunning" class="text-weight-medium q-mt-xs" data-testid="players-server-running">
        {{ t('playerFiles.serverRunning') }}
      </div>
    </q-banner>

    <q-banner v-if="error" rounded class="bg-negative text-white q-mb-md" data-testid="players-error">
      {{ error }}
      <template #action><q-btn flat :label="t('playerFiles.retry')" @click="init" /></template>
    </q-banner>

    <div class="row items-center q-gutter-md q-mb-sm">
      <q-input
        v-model="search"
        dense
        outlined
        clearable
        debounce="300"
        style="min-width: 260px"
        :label="t('playerFiles.search')"
        data-testid="players-search"
        @update:model-value="reload"
      >
        <template #prepend><q-icon :name="mdiMagnify" /></template>
      </q-input>
      <q-btn flat round :icon="mdiRefresh" :aria-label="t('playerFiles.reload')" @click="reload">
        <q-tooltip>{{ t('playerFiles.reload') }}</q-tooltip>
      </q-btn>
    </div>

    <q-table
      v-if="info"
      v-model:pagination="pagination"
      :rows="rows"
      :columns="columns"
      row-key="id"
      dense
      flat
      bordered
      binary-state-sort
      :loading="loading"
      :rows-per-page-options="[10, 25, 50, 100]"
      :no-data-label="t('playerFiles.empty')"
      data-testid="players-table"
      @request="onRequest"
      @row-dblclick="(_evt: Event, row: IPlayerSummary) => open(row)"
    >
      <template #body-cell-name="{ row, value }">
        <q-td>
          <span class="text-weight-medium">{{ value }}</span>
          <q-chip v-if="row.problem" dense color="negative" text-color="white" class="q-ml-sm" data-testid="player-problem">
            {{ problemLabel(row.problem) }}
          </q-chip>
        </q-td>
      </template>
      <template #body-cell-actions="{ row }">
        <q-td auto-width>
          <q-btn
            flat
            round
            dense
            :icon="mdiCardAccountDetails"
            :aria-label="t('playerFiles.open', { name: row.name })"
            :data-testid="`player-open-${row.id}`"
            @click="open(row)"
          >
            <q-tooltip>{{ t('playerFiles.open', { name: row.name }) }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </q-table>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn, QTableProps } from 'quasar'
import { mdiAlertOutline, mdiCardAccountDetails, mdiMagnify, mdiRefresh } from '@quasar/extras/mdi-v7'
import { describeError } from '../../players/helpers/describe-error'
import { formatCell } from '../helpers/format'
import { getPlayersInfo, getPlayersStatus, listPlayers } from '../services/player-files-api'
import type { IPlayerSummary, IPlayersInfo, IPlayersStatus } from '../types/player-files'
import PlayerDetailDialog from '../components/PlayerDetailDialog.vue'

const { t, te, locale } = useI18n()
const $q = useQuasar()

const info = ref<IPlayersInfo>()
const status = ref<IPlayersStatus>()
const rows = ref<IPlayerSummary[]>([])
const loading = ref(false)
const error = ref('')
const search = ref<string | null>('')
const pagination = ref({ page: 1, rowsPerPage: 25, sortBy: 'name', descending: false, rowsNumber: 0 })

/** Etichetta tradotta di una chiave dichiarata dall'adapter (ripiega sul nome). */
function labelOf(key: string, fallback: string): string {
  return te(key) ? t(key) : fallback
}

/**
 * Testo del codice di problema di un file (`playerFiles.problems.<codice>`, altrimenti il codice).
 *
 * @param code - codice stabile dell'adapter
 */
function problemLabel(code: string): string {
  return labelOf(`playerFiles.problems.${code}`, code)
}

/** Colonne generate dal descrittore + la colonna delle azioni. */
const columns = computed<QTableColumn<IPlayerSummary>[]>(() => [
  ...(info.value?.columns ?? []).map((column) => ({
    name: column.name,
    label: labelOf(column.labelKey, column.name),
    align: column.type === 'number' || column.type === 'duration' ? ('right' as const) : ('left' as const),
    sortable: column.sortable,
    field: (row: IPlayerSummary) => (column.source === 'extra' ? row.extra[column.name] : (row as unknown as Record<string, unknown>)[column.name]),
    format: (value: unknown) => formatCell(value, column.type, locale.value, t('playerFiles.yes'), t('playerFiles.no')),
  })),
  { name: 'actions', label: '', field: 'id', align: 'right' as const },
])

/** Carica una pagina dell'elenco con la paginazione corrente. */
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const p = pagination.value
    const params: Record<string, string | number> = { page: p.page, pageSize: p.rowsPerPage }
    if (p.sortBy) params.orderBy = `${p.descending ? '-' : ''}${p.sortBy}`
    if (search.value) params.search = search.value
    const page = await listPlayers(params)
    rows.value = page.items
    pagination.value.rowsNumber = page.total
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    loading.value = false
  }
}

/** Torna alla prima pagina e ricarica (ricerca o ricarica manuale). */
function reload(): void {
  pagination.value.page = 1
  void load()
}

/**
 * Cambio di pagina, ordinamento o dimensione (paginazione lato server).
 *
 * @param props - richiesta della tabella
 */
function onRequest(props: Parameters<NonNullable<QTableProps['onRequest']>>[0]): void {
  const { page, rowsPerPage, sortBy, descending } = props.pagination
  pagination.value = { ...pagination.value, page, rowsPerPage, sortBy: sortBy ?? 'name', descending }
  void load()
}

/**
 * Apre il dettaglio del giocatore.
 *
 * @param row - riga scelta
 */
function open(row: IPlayerSummary): void {
  $q.dialog({ component: PlayerDetailDialog, componentProps: { playerId: row.id, playerName: row.name } }).onDismiss(() => void load()) // le modifiche cambiano i valori dell'elenco
}

/** Descrittore, stato del server ed elenco. */
async function init(): Promise<void> {
  error.value = ''
  try {
    info.value = await getPlayersInfo()
  } catch (e) {
    error.value = await describeError(e)
    return
  }
  getPlayersStatus()
    .then((s) => (status.value = s))
    .catch(() => undefined) // stato non rilevabile: resta l'avviso generico
  await load()
}

onMounted(() => void init())
</script>
