<template>
  <div data-testid="panel-live-inventory">
    <q-banner rounded class="bg-blue-1 text-black q-mb-sm" role="note" data-testid="live-inventory-note">
      <q-badge color="negative" class="q-mr-sm" data-testid="live-inventory-badge">{{ t('playerFiles.liveInv.live') }}</q-badge>
      {{ t('playerFiles.liveInv.note') }}
    </q-banner>
    <q-banner v-if="error" rounded class="bg-negative text-white q-mb-sm" role="alert" data-testid="live-inventory-error">{{ error }}</q-banner>
    <q-banner v-if="notice" rounded class="bg-orange-2 text-black q-mb-sm" role="alert" data-testid="live-inventory-notice">{{ notice }}</q-banner>
    <q-banner v-if="warning" rounded class="bg-warning text-black q-mb-sm" role="alert" data-testid="live-inventory-warning">
      {{ warning }}
      <template #action><q-btn flat :label="t('playerFiles.liveInv.dismiss')" @click="warning = ''" /></template>
    </q-banner>
    <div v-if="inventory" class="text-caption q-mb-sm" data-testid="live-inventory-weight">
      {{ t('playerFiles.liveInv.weight', { weight: inventory.carryWeight, items: inventory.carryItems }) }}
      <span v-if="inventory.truncated"> · {{ t('playerFiles.liveInv.truncated') }}</span>
    </div>

    <div class="row items-start q-col-gutter-sm q-mb-sm">
      <template v-if="canWrite">
        <div class="col-12 col-md-7">
          <q-select
            v-model="picked"
            :options="found"
            :label="t('playerFiles.inventory.pick')"
            use-input
            input-debounce="250"
            dense
            outlined
            option-label="label"
            data-testid="live-inventory-pick"
            @filter="onFilter"
          >
            <template #no-option>
              <q-item><q-item-section class="text-grey">{{ t('playerFiles.inventory.pickNone') }}</q-item-section></q-item>
            </template>
          </q-select>
        </div>
        <div class="col-auto">
          <q-btn color="primary" :icon="mdiPlus" :label="t('playerFiles.inventory.addConfirm')" :disable="!picked || busy" data-testid="live-inventory-add" @click="add()" />
        </div>
      </template>
      <q-space />
      <div class="col-auto">
        <q-btn flat dense round :icon="mdiRefresh" :aria-label="t('playerFiles.reload')" :loading="loading" data-testid="live-inventory-reload" @click="reload()" />
      </div>
    </div>

    <pachi-table2
      :rows="inventory?.items ?? []"
      :columns="columns"
      row-key="ref"
      dense
      :loading="loading"
      single-sort
      :initial-sort="[]"
      :auto-height="false"
      :no-data-label="t('playerFiles.inventory.empty')"
      data-testid="live-inventory-table"
    >
      <template #body-cell-name="{ slotProps: { row } }">
        <q-td :data-testid="`live-inventory-name-${row.ref}`">
          <span :style="{ paddingLeft: `${row.depth * 16}px` }">{{ row.shortDescription || row.name || '—' }}</span>
        </q-td>
      </template>
      <template #body-cell-actions="{ slotProps: { row } }">
        <q-td auto-width>
          <template v-if="canEdit">
            <q-btn flat round dense color="primary" :icon="mdiPencil" :aria-label="t('playerFiles.liveInv.editItem', { name: row.shortDescription })" :data-testid="`live-inventory-edit-${row.ref}`" @click="edit(row.ref)">
              <q-tooltip>{{ t('playerFiles.liveInv.editItem', { name: row.shortDescription }) }}</q-tooltip>
            </q-btn>
            <q-btn flat round dense color="negative" :icon="mdiDelete" :aria-label="t('playerFiles.inventory.remove', { name: row.shortDescription })" :data-testid="`live-inventory-remove-${row.ref}`" @click="remove(row)">
              <q-tooltip>{{ t('playerFiles.inventory.remove', { name: row.shortDescription }) }}</q-tooltip>
            </q-btn>
          </template>
        </q-td>
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
/**
 * Inventario ed equipaggiamento LIVE di un giocatore connesso (`player.inventory`): tabella con annidamento, aggiunta da un prototipo
 * (`load.obj`, con l'avviso `vnum_not_saveable`), modifica (dialogo `LiveItemEditDialog`) e rimozione con conferma. Ogni scrittura usa il
 * `ref` e l'impronta dell'ULTIMA lettura della stessa riga; su `stale_ref` si ricarica l'elenco e si avvisa, senza ripetere nulla.
 * Se il canale non risponde al primo caricamento emette `unavailable` (il chiamante ripiega sull'inventario su file).
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiDelete, mdiPencil, mdiPlus, mdiRefresh } from '@quasar/extras/mdi-v7'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import { describeError } from '../../players/helpers/describe-error'
import { listObjects } from '../../objects/services/objects-api'
import { errorCode } from '../helpers/error-code'
import { loadLiveEnums } from '../helpers/live-enums'
import { useMaxRentVnum, type IEnumOpt } from '../helpers/live-item'
import { getLiveInventory, loadLive, removeLiveItem } from '../services/live-api'
import type { ILiveInventory, ILiveItem } from '../types/live'
import LiveItemEditDialog from './LiveItemEditDialog.vue'

const props = defineProps<{
  /** Nome del personaggio connesso. */
  playerName: string
  /** Si possono modificare e togliere oggetti (`obj.set`/`obj.remove` attivi, mondo scrivibile). */
  canEdit: boolean
  /** Si possono creare oggetti (`load.obj`). */
  canWrite: boolean
}>()

const emit = defineEmits<{
  /** Il canale non risponde: usare l'inventario su file. */
  unavailable: []
}>()

const { t } = useI18n()
const $q = useQuasar()
const maxRentVnum = useMaxRentVnum()

const inventory = ref<ILiveInventory>()
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const warning = ref('')
const enums = ref<Record<string, IEnumOpt[]>>({})
const picked = ref<{ value: number; label: string } | null>(null)
const found = ref<{ value: number; label: string }[]>([])

/** Nome dello slot di equipaggiamento (enum del mondo, altrimenti il numero). */
function slotLabel(slot: number | null): string {
  if (slot === null) return t('playerFiles.inventory.carried')
  const name = enums.value.dikumodWearPos?.find((o) => o.value === slot)?.label
  return name ? t(`playerFiles.slots.${name}`, name) : t('playerFiles.liveInv.slotN', { n: slot })
}

const columns = computed<QTableColumn<ILiveItem>[]>(() => [
  { name: 'vnum', label: t('playerFiles.inventory.vnum'), field: 'vnum', align: 'left', format: (v: number | null) => (v === null ? '—' : String(v)) },
  { name: 'name', label: t('playerFiles.inventory.name'), field: 'shortDescription', align: 'left' },
  { name: 'where', label: t('playerFiles.inventory.where'), field: 'slot', align: 'left', format: (_v: number | null, row: ILiveItem) => (row.depth > 0 ? t('playerFiles.inventory.inContainer') : slotLabel(row.slot)) },
  ...(props.canEdit ? [{ name: 'actions', label: '', field: 'ref' as const, align: 'right' as const }] : []),
])

/**
 * Rilegge l'elenco dal gioco.
 *
 * @param first - primo caricamento: se il canale non risponde si segnala `unavailable`
 */
async function reload(first = false): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    inventory.value = await getLiveInventory(props.playerName)
  } catch (e) {
    const code = await errorCode(e)
    if (first && code && ['worldlive.unreachable', 'worldlive.timeout', 'worldlive.command_disabled', 'worldlive.auth_failed', 'worldlive.token_missing'].includes(code)) {
      emit('unavailable')
      return
    }
    error.value = await describeError(e)
  } finally {
    loading.value = false
  }
}

/**
 * Cerca prototipi per nome o vnum; quelli oltre il vnum massimo del rent restano visibili ma non selezionabili.
 *
 * @param text - testo digitato
 * @param update - callback di q-select
 */
function onFilter(text: string, update: (fn: () => void) => void): void {
  void listObjects({ search: text, pageSize: 20 })
    .then((page) =>
      page.items.map((o) => {
        const unsafe = o.vnum > maxRentVnum.value
        return { value: o.vnum, label: `#${o.vnum} ${o.shortDescription}${unsafe ? ` — ${t('playerFiles.liveInv.notSaveable')}` : ''}` }
      }),
    )
    .catch(() => [])
    .then((items) => update(() => (found.value = items)))
}

/** Crea l'oggetto scelto nell'inventario del giocatore e mostra gli avvisi del gioco (`vnum_not_saveable`). */
async function add(): Promise<void> {
  const choice = picked.value
  if (!choice) return
  busy.value = true
  error.value = notice.value = warning.value = ''
  try {
    const out = await loadLive('obj', { vnum: choice.value, player: props.playerName, count: 1, notify: false })
    if (out.warnings.includes('vnum_not_saveable')) warning.value = t('playerFiles.liveInv.vnumNotSaveable', { vnum: choice.value })
    picked.value = null
    await reload()
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    busy.value = false
  }
}

/** Dopo uno `stale_ref`: avvisa e ricarica l'elenco. */
async function onStale(): Promise<void> {
  notice.value = t('playerFiles.liveInv.stale')
  await reload()
}

/**
 * Apre il dialogo di modifica dell'oggetto; alla chiusura rilegge l'elenco.
 *
 * @param ref - riferimento dell'oggetto, dall'ultima lettura
 */
function edit(ref: string): void {
  notice.value = ''
  $q.dialog({ component: LiveItemEditDialog, componentProps: { playerName: props.playerName, itemRef: ref, onStale: () => void onStale() } }).onDismiss(() => void reload())
}

/**
 * Toglie e DISTRUGGE l'oggetto dopo conferma (con il contenuto, se contenitore).
 *
 * @param row - riga dell'ultima lettura (porta `ref` e impronta)
 */
function remove(row: ILiveItem): void {
  notice.value = ''
  $q.dialog({
    title: t('playerFiles.liveInv.removeTitle'),
    message: t(row.contents > 0 ? 'playerFiles.liveInv.removeConfirmContents' : 'playerFiles.liveInv.removeConfirm', { name: row.shortDescription, n: row.contents }),
    cancel: t('playerFiles.cancel'),
    ok: { label: t('playerFiles.inventory.removeOk'), color: 'negative', 'data-testid': 'live-inventory-remove-confirm' },
    persistent: true,
  }).onOk(() => {
    void (async () => {
      error.value = ''
      try {
        await removeLiveItem(props.playerName, row.ref, { vnum: row.vnum, fp: row.fp })
        await reload()
      } catch (e) {
        if ((await errorCode(e)) === 'worldlive.stale_ref') await onStale()
        else error.value = await describeError(e)
      }
    })()
  })
}

onMounted(async () => {
  enums.value = await loadLiveEnums()
  await reload(true)
})

defineExpose({ reload })
</script>
