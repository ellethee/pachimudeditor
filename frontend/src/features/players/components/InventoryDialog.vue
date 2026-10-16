<template>
  <q-dialog ref="dialogRef" @hide="onDialogHide">
    <q-card style="min-width: 640px; max-width: 95vw">
      <q-card-section class="row items-center">
        <div class="text-h6">{{ t('players.inventory.title', { name: characterName }) }}</div>
        <q-space />
        <q-btn flat round dense :icon="mdiClose" :aria-label="t('players.close')" @click="onDialogCancel" />
      </q-card-section>
      <q-card-section class="q-pt-none">
        <q-banner v-if="error" class="bg-negative text-white q-mb-sm" rounded>{{ error }}</q-banner>
        <q-table
          :rows="items"
          :columns="columns"
          row-key="id"
          dense
          flat
          bordered
          :loading="loading"
          :rows-per-page-options="[0]"
          hide-pagination
          :no-data-label="t('players.inventory.empty')"
        >
          <template #body-cell-actions="{ row }">
            <q-td auto-width>
              <q-btn
                v-if="row.containerInstanceId === null"
                flat
                round
                dense
                :icon="mdiShieldHalfFull"
                :aria-label="t('players.inventory.slot')"
                @click="editSlot(row)"
              />
              <q-btn flat round dense :icon="mdiDelete" :aria-label="t('players.inventory.remove')" @click="remove(row)" />
            </q-td>
          </template>
        </q-table>
      </q-card-section>
      <q-card-actions align="between">
        <q-btn flat :icon="mdiPlus" :label="t('players.inventory.add')" color="primary" @click="addItem" />
        <q-btn flat :label="t('players.close')" @click="onDialogCancel" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialogPluginComponent, useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiClose, mdiDelete, mdiPlus, mdiShieldHalfFull } from '@quasar/extras/mdi-v7'
import { describeError } from '../helpers/describe-error'
import {
  addInventoryItem,
  listInventory,
  removeInventoryItem,
  searchObjects,
  setItemSlot,
} from '../services/players-api'
import type { IInventoryItem, IObjectRef } from '../types/players'
import PickerDialog from './PickerDialog.vue'

const props = defineProps<{
  /** Id del personaggio. */
  characterId: number
  /** Nome del personaggio (titolo). */
  characterName: string
}>()

defineEmits([...useDialogPluginComponent.emits])

const { t } = useI18n()
const $q = useQuasar()
const { dialogRef, onDialogHide, onDialogCancel } = useDialogPluginComponent()
const items = ref<IInventoryItem[]>([])
const loading = ref(false)
const error = ref('')

const columns = computed<QTableColumn<IInventoryItem>[]>(() => [
  { name: 'vnum', label: t('players.inventory.vnum'), field: 'vnum', align: 'left', sortable: true },
  { name: 'name', label: t('players.inventory.name'), field: 'shortDescription', align: 'left' },
  {
    name: 'where',
    label: t('players.inventory.where'),
    field: (row: IInventoryItem) =>
      row.containerInstanceId !== null
        ? t('players.inventory.inContainer', { id: row.containerInstanceId })
        : (row.equippedSlot ?? t('players.inventory.carried')),
    align: 'left',
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
])

/** Ricarica l'inventario dal backend. */
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    items.value = await listInventory(props.characterId)
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    loading.value = false
  }
}

/**
 * Esegue un'azione sul backend e ricarica; gli errori finiscono nel banner.
 *
 * @param action - chiamata da eseguire
 */
async function run(action: () => Promise<unknown>): Promise<void> {
  try {
    await action()
    await load()
  } catch (e) {
    error.value = await describeError(e)
  }
}

/** Apre il selettore di prototipi e aggiunge l'oggetto scelto. */
function addItem(): void {
  $q.dialog({
    component: PickerDialog,
    componentProps: {
      title: t('players.inventory.add'),
      label: t('players.inventory.pickObject'),
      confirmLabel: t('players.inventory.add'),
      search: searchObjects,
      optionLabel: (o: IObjectRef) => `${o.vnum} - ${o.shortDescription}`,
    },
  }).onOk((prototypeId: number) => void run(() => addInventoryItem(props.characterId, prototypeId)))
}

/**
 * Chiede lo slot di equipaggiamento (vuoto = non equipaggiato).
 *
 * @param row - oggetto da modificare
 */
function editSlot(row: IInventoryItem): void {
  $q.dialog({
    title: t('players.inventory.slot'),
    message: t('players.inventory.slotHint', { name: row.shortDescription }),
    prompt: { model: row.equippedSlot ?? '', type: 'text' },
    cancel: true,
    persistent: true,
  }).onOk((slot: string) =>
    void run(() => setItemSlot(props.characterId, row.id, slot.trim() === '' ? null : slot.trim())),
  )
}

/**
 * Conferma e rimuove l'oggetto (con il suo contenuto).
 *
 * @param row - oggetto da rimuovere
 */
function remove(row: IInventoryItem): void {
  $q.dialog({
    title: t('players.inventory.remove'),
    message: t('players.inventory.removeConfirm', { name: row.shortDescription }),
    cancel: true,
    persistent: true,
  }).onOk(() => void run(() => removeInventoryItem(props.characterId, row.id)))
}

onMounted(load)
</script>
