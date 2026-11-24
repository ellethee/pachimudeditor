<template>
  <div data-testid="panel-inventory">
    <q-banner v-if="error" rounded class="bg-negative text-white q-mb-sm" data-testid="inventory-error">
      {{ error }}
      <template v-if="conflict" #action>
        <q-btn flat :label="t('playerFiles.edit.reload')" data-testid="inventory-reload" @click="reload" />
      </template>
    </q-banner>
    <q-banner v-if="inventory?.problem" rounded class="bg-warning text-black q-mb-sm" data-testid="inventory-problem">
      {{ problemLabel(inventory.problem) }}
    </q-banner>
    <div v-if="rentInfo" class="text-caption q-mb-sm" data-testid="inventory-rent">{{ rentInfo }}</div>

    <div v-if="canWrite" class="q-mb-sm">
      <q-btn
        v-if="!adding"
        outline
        color="primary"
        :icon="mdiPlus"
        :label="t('playerFiles.inventory.add')"
        :disable="blocked"
        data-testid="inventory-add"
        @click="adding = true"
      />
      <div v-else class="row items-start q-col-gutter-sm" data-testid="inventory-add-form">
        <div class="col-12 col-md-5">
          <q-select
            v-model="picked"
            :options="found"
            :label="t('playerFiles.inventory.pick')"
            use-input
            input-debounce="250"
            dense
            outlined
            option-label="label"
            option-disable="disable"
            data-testid="inventory-pick"
            @filter="onFilter"
          >
            <template #no-option>
              <q-item><q-item-section class="text-grey">{{ t('playerFiles.inventory.pickNone') }}</q-item-section></q-item>
            </template>
          </q-select>
        </div>
        <div class="col-6 col-md-3">
          <q-select
            v-model="newSlot"
            :options="slotOptions"
            emit-value
            map-options
            dense
            outlined
            :label="t('playerFiles.inventory.where')"
            :disable="newContainer !== null"
            data-testid="inventory-add-slot"
          />
        </div>
        <div class="col-6 col-md-2">
          <q-select
            v-model="newContainer"
            :options="containerOptions"
            emit-value
            map-options
            dense
            outlined
            clearable
            :label="t('playerFiles.inventory.container')"
            data-testid="inventory-add-container"
          />
        </div>
        <div class="col-12 col-md-2">
          <q-btn color="primary" :label="t('playerFiles.inventory.addConfirm')" :disable="!picked || blocked" data-testid="inventory-add-confirm" @click="add" />
          <q-btn flat :label="t('playerFiles.cancel')" @click="adding = false" />
        </div>
      </div>
    </div>

    <pachi-table2
      :rows="inventory?.items ?? []"
      :columns="columns"
      row-key="id"
      dense
      :loading="loading"
      single-sort
      :initial-sort="[]"
      :no-data-label="t('playerFiles.inventory.empty')"
      data-testid="inventory-table"
    >
      <template #body-cell-name="{ slotProps: { row } }">
        <q-td>
          <span :style="{ paddingLeft: `${row.depth * 16}px` }">{{ row.name || '—' }}</span>
          <q-chip v-if="!row.known" dense color="grey-6" text-color="white" class="q-ml-sm">
            {{ t('playerFiles.inventory.unknown') }}
          </q-chip>
        </q-td>
      </template>
      <template #body-cell-where="{ slotProps: { row } }">
        <q-td>
          <q-select
            v-if="canWrite && row.depth === 0"
            :model-value="row.wearSlot"
            :options="slotOptions"
            emit-value
            map-options
            dense
            borderless
            :disable="blocked"
            :aria-label="t('playerFiles.inventory.where')"
            :data-testid="`inventory-slot-${row.id}`"
            @update:model-value="(slot: string | null) => changeSlot(row.id, slot)"
          />
          <span v-else>{{ whereOf(row) }}</span>
        </q-td>
      </template>
      <template #body-cell-actions="{ slotProps: { row } }">
        <q-td auto-width>
          <q-btn
            flat
            round
            dense
            color="negative"
            :icon="mdiDelete"
            :disable="blocked"
            :aria-label="t('playerFiles.inventory.remove', { name: row.name })"
            :data-testid="`inventory-remove-${row.id}`"
            @click="remove(row)"
          >
            <q-tooltip>{{ t('playerFiles.inventory.remove', { name: row.name }) }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
/**
 * Inventario ed equipaggiamento di un giocatore: lettura e, se il mondo lo permette, aggiunta (da un prototipo del mondo),
 * cambio di slot e rimozione. Ogni scrittura manda la `revision` letta e la conferma del server acceso.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiDelete, mdiPlus } from '@quasar/extras/mdi-v7'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import { describeError } from '../../players/helpers/describe-error'
import { listObjects } from '../../objects/services/objects-api'
import { errorCode } from '../helpers/error-code'
import { useMaxRentVnum } from '../helpers/live-item'
import { addPlayerItem, getPlayerInventory, removePlayerItem, updatePlayerItem } from '../services/player-files-api'
import type { IPlayerInventory, IPlayerItem } from '../types/player-files'

const props = defineProps<{
  /** Id opaco del giocatore. */
  playerId: string
  /** Il mondo permette di modificare l'inventario. */
  canWrite: boolean
  /** Slot ammessi (`PlayersInfo.wearSlots`). */
  wearSlots: string[]
  /** Il server è acceso e la conferma non è stata data: le scritture sono disabilitate. */
  blocked?: boolean
  /** Conferma del server acceso da mandare con ogni scrittura. */
  confirmServerRunning?: boolean
}>()

const { t, te } = useI18n()
const $q = useQuasar()
const maxRentVnum = useMaxRentVnum()

const inventory = ref<IPlayerInventory>()
const loading = ref(false)
const error = ref('')
const conflict = ref(false)
const adding = ref(false)
const picked = ref<{ value: number; label: string; disable: boolean } | null>(null)
const found = ref<{ value: number; label: string; disable: boolean }[]>([])
const newSlot = ref<string | null>(null)
const newContainer = ref<number | null>(null)

/** Etichetta tradotta (ripiega sul nome). */
function labelOf(key: string, fallback: string): string {
  return te(key) ? t(key) : fallback
}

/** Testo di un codice di problema del file. */
function problemLabel(code: string): string {
  return labelOf(`playerFiles.problems.${code}`, code)
}

/** Dove si trova un oggetto (slot, contenitore o inventario). */
function whereOf(row: IPlayerItem): string {
  if (row.wearSlot) return labelOf(`playerFiles.slots.${row.wearSlot}`, row.wearSlot)
  return row.depth > 0 ? t('playerFiles.inventory.inContainer') : t('playerFiles.inventory.carried')
}

/** Opzioni di slot: «portato» (`null`) e gli slot del MUD. */
const slotOptions = computed(() => [
  { value: null, label: t('playerFiles.inventory.carried') },
  ...props.wearSlots.map((slot) => ({ value: slot, label: labelOf(`playerFiles.slots.${slot}`, slot) })),
])

/** Contenitori possibili: gli oggetti del giocatore di tipo contenitore. */
const containerOptions = computed(() =>
  (inventory.value?.items ?? [])
    .filter((item) => item.extra.itemType === 'container')
    .map((item) => ({ value: item.id, label: `${item.name} (#${item.id})` })),
)

const columns = computed<QTableColumn[]>(() => [
  { name: 'vnum', label: t('playerFiles.inventory.vnum'), field: 'vnum', align: 'left' },
  { name: 'name', label: t('playerFiles.inventory.name'), field: 'name', align: 'left' },
  { name: 'where', label: t('playerFiles.inventory.where'), field: 'wearSlot', align: 'left' },
  ...(props.canWrite ? [{ name: 'actions', label: '', field: 'id', align: 'right' as const }] : []),
])

/** Riga con testata del rent («oro lasciato», «costo giornaliero»), se il file esiste. */
const rentInfo = computed(() => {
  const extra = inventory.value?.extra
  if (!extra || extra.rentFile !== true) return ''
  return t('playerFiles.inventory.rent', { gold: extra.goldLeft ?? 0, cost: extra.totalCost ?? 0, n: extra.declaredNumber ?? 0 })
})

/** Carica (o ricarica) l'inventario. */
async function reload(): Promise<void> {
  loading.value = true
  error.value = ''
  conflict.value = false
  try {
    inventory.value = await getPlayerInventory(props.playerId)
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    loading.value = false
  }
}

/**
 * Esegue una scrittura: aggiorna l'inventario con la risposta o mostra l'errore (con «ricarica» se il file è cambiato).
 *
 * @param action - chiamata API che restituisce il nuovo inventario
 * @returns `true` se riuscita
 */
async function run(action: () => Promise<IPlayerInventory>): Promise<boolean> {
  error.value = ''
  conflict.value = false
  try {
    inventory.value = await action()
    return true
  } catch (e) {
    conflict.value = (await errorCode(e)) === 'worldplayers.conflict'
    error.value = await describeError(e)
    return false
  }
}

/** Opzioni di scrittura correnti. */
function options() {
  return { revision: inventory.value?.revision ?? null, confirmServerRunning: props.confirmServerRunning === true }
}

/**
 * Cerca prototipi per nome o vnum (catalogo oggetti del mondo).
 *
 * @param text - testo digitato
 * @param update - callback di q-select
 */
function onFilter(text: string, update: (fn: () => void) => void): void {
  void listObjects({ search: text, pageSize: 20 })
    .then((page) =>
      page.items.map((o) => {
        const unsafe = o.vnum > maxRentVnum.value // il rent salva il vnum in uno `short`: l'oggetto non e' scrivibile nel file
        return { value: o.vnum, label: `#${o.vnum} ${o.shortDescription}${unsafe ? ` — ${t('playerFiles.inventory.notSaveable')}` : ''}`, disable: unsafe }
      }),
    )
    .catch(() => [])
    .then((items) => update(() => (found.value = items)))
}

/** Aggiunge l'oggetto scelto con slot o contenitore. */
async function add(): Promise<void> {
  if (!picked.value) return
  const ok = await run(() =>
    addPlayerItem(props.playerId, {
      ...options(),
      vnum: picked.value!.value,
      wearSlot: newContainer.value === null ? newSlot.value : null,
      containerId: newContainer.value,
    }),
  )
  if (ok) {
    adding.value = false
    picked.value = null
    newSlot.value = null
    newContainer.value = null
  }
}

/**
 * Cambia lo slot di un oggetto.
 *
 * @param itemId - posizione dell'oggetto
 * @param slot - nuovo slot (`null` = portato)
 */
async function changeSlot(itemId: number, slot: string | null): Promise<void> {
  await run(() => updatePlayerItem(props.playerId, itemId, slot, options()))
}

/**
 * Toglie l'oggetto (con il suo contenuto) dopo conferma.
 *
 * @param row - oggetto da togliere
 */
function remove(row: IPlayerItem): void {
  $q.dialog({
    title: t('playerFiles.inventory.removeTitle'),
    message: t('playerFiles.inventory.removeConfirm', { name: row.name }),
    cancel: t('playerFiles.cancel'),
    ok: { label: t('playerFiles.inventory.removeOk'), color: 'negative' },
    persistent: true,
  }).onOk(() => void run(() => removePlayerItem(props.playerId, row.id, options())))
}

onMounted(() => void reload())
</script>
