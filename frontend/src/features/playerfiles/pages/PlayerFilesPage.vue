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
      >
        <template #prepend><q-icon :name="mdiMagnify" /></template>
      </q-input>
      <q-btn flat round :icon="mdiRefresh" :aria-label="t('playerFiles.reload')" @click="load">
        <q-tooltip>{{ t('playerFiles.reload') }}</q-tooltip>
      </q-btn>
      <template v-if="live.enabled.value">
        <q-chip dense :color="liveColor" text-color="white" :icon="mdiServerNetwork" role="status" data-testid="live-status">
          {{ liveLabel }}
          <q-tooltip v-if="!live.connected.value">{{ t('playerFiles.live.fallback') }}</q-tooltip>
        </q-chip>
        <q-btn
          v-if="live.connected.value"
          outline
          dense
          color="primary"
          :label="t('playerFiles.live.server.open')"
          data-testid="live-open"
          @click="openLive"
        />
      </template>
    </div>

    <pachi-table2
      v-if="info && ready"
      ref="table"
      url="/api/world/players"
      :columns="columns"
      :can-edit="typed"
      :extra-params="extraParams"
      hide-toolbar
      error-banner
      dense
      data-testid="players-table"
      @row-dblclick="(_evt: Event, row: IPlayerSummary) => open(row)"
    >
      <template #error="{ error: loadError, retry }">
        <table-error :error="loadError" :retry="retry" />
      </template>
      <template #body-cell-name="{ slotProps }">
        <q-td :props="slotProps">
          <span class="text-weight-medium">{{ slotProps.value }}</span>
          <q-chip
            v-if="slotProps.row.online === true"
            dense
            :color="slotProps.row.extra.liveState === 'playing' ? 'positive' : 'orange'"
            text-color="white"
            class="q-ml-sm"
            :data-testid="`player-online-${slotProps.row.id}`"
          >
            {{ slotProps.row.extra.liveState === 'playing' || !slotProps.row.extra.liveState ? t('playerFiles.live.online') : t('playerFiles.live.state.' + String(slotProps.row.extra.liveState)) }}
          </q-chip>
          <q-chip v-if="slotProps.row.problem" dense color="negative" text-color="white" class="q-ml-sm" data-testid="player-problem">
            {{ problemLabel(slotProps.row.problem) }}
          </q-chip>
        </q-td>
      </template>
      <template #body-cell-actions="{ slotProps }">
        <q-td :props="slotProps" auto-width>
          <q-btn
            flat
            round
            dense
            :icon="mdiCardAccountDetails"
            :aria-label="t('playerFiles.open', { name: slotProps.row.name })"
            :data-testid="`player-open-${slotProps.row.id}`"
            @click="open(slotProps.row)"
          >
            <q-tooltip>{{ t('playerFiles.open', { name: slotProps.row.name }) }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiAlertOutline, mdiCardAccountDetails, mdiMagnify, mdiRefresh, mdiServerNetwork } from '@quasar/extras/mdi-v7'
import { describeError } from '../../players/helpers/describe-error'
import { formatCell } from '../helpers/format'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import type { PachiTable2Exposed } from '@ilpachi/pachi-kit/table'
import TableError from '../../shared/components/TableError.vue'
import { getPlayersInfo, getPlayersStatus } from '../services/player-files-api'
import type { IPlayerSummary, IPlayersInfo, IPlayersStatus } from '../types/player-files'
import PlayerDetailDialog from '../components/PlayerDetailDialog.vue'
import LiveServerDialog from '../components/LiveServerDialog.vue'
import { ensureWorlds } from '../../shared/helpers/world-state'
import { useLive } from '../helpers/live-state'

const { t, te, locale } = useI18n()
const $q = useQuasar()
const live = useLive()

const info = ref<IPlayersInfo>()
const status = ref<IPlayersStatus>()
const table = ref<PachiTable2Exposed<IPlayerSummary> | null>(null)
/** La tabella compare dopo il descrittore e lo stato live (la colonna `online` dipende dal canale). */
const ready = ref(false)
const error = ref('')
const search = ref<string | null>('')
/** Serve solo a tipizzare la tabella su `IPlayerSummary` (stesso espediente di `AccountsPanel`). */
const typed = (_row: IPlayerSummary): boolean => true

/** La ricerca viaggia come parametro extra (la barra della tabella è nascosta). */
const extraParams = computed<Record<string, unknown>>(() => (search.value ? { search: search.value } : {}))

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

/** Ricarica l'elenco (pulsante, chiusura dei dialoghi: le modifiche cambiano i valori). */
function load(): void {
  void table.value?.api.reload()
}

/**
 * Apre il dettaglio del giocatore.
 *
 * @param row - riga scelta
 */
function open(row: IPlayerSummary): void {
  $q.dialog({ component: PlayerDetailDialog, componentProps: { playerId: row.id, playerName: row.name } }).onDismiss(load) // le modifiche cambiano i valori dell'elenco
}

/** Colore del chip dello stato del canale live. */
const liveColor = computed(() => (live.connected.value ? 'positive' : 'grey-7'))
/** Testo dello stato del canale live (mai un errore: senza canale i dati vengono dai file). */
const liveLabel = computed(() => {
  const state = live.status.value?.state
  if (!state) return t('playerFiles.live.channel.unknown')
  const latency = live.status.value?.latencyMs
  return t(`playerFiles.live.channel.${state}`, { ms: latency ?? '?' })
})

/** Apre il pannello «Server live»; alla chiusura rilegge elenco e stato (le azioni possono cambiare i dati). */
function openLive(): void {
  $q.dialog({ component: LiveServerDialog }).onDismiss(() => {
    void live.refresh()
    load()
  })
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
  await ensureWorlds()
  if (live.enabled.value) await live.refresh() // prima dell'elenco: `online` dipende dal canale
  ready.value = true
}

onMounted(() => void init())
</script>
