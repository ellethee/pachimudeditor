<template>
  <pachi-dialog ref="dialogRef" :title="title" min-width="420px" max-width="95vw" @hide="onDialogHide()">
      <div>
        <q-select
          v-model="selected"
          :options="options"
          option-value="id"
          :option-label="optionLabel"
          :label="label"
          :hint="t('players.picker.hint')"
          :loading="loading"
          use-input
          input-debounce="300"
          outlined
          dense
          autofocus
          @filter="onFilter"
        >
          <template #no-option>
            <q-item>
              <q-item-section class="text-grey">{{ t('players.picker.noResults') }}</q-item-section>
            </q-item>
          </template>
        </q-select>
      </div>
      <template #actions>
        <q-btn flat :label="t('players.cancel')" @click="onDialogCancel" />
        <q-btn color="primary" :label="confirmLabel" :disable="!selected" @click="onDialogOK(selected?.id)" />
      </template>
  </pachi-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialogPluginComponent } from 'quasar'
import { PachiDialog } from '@ilpachi/pachi-kit/dialog'

/** Elemento minimo selezionabile. */
interface IPickable {
  id: number
}

const props = defineProps<{
  /** Titolo del dialog. */
  title: string
  /** Etichetta della select. */
  label: string
  /** Etichetta del pulsante di conferma. */
  confirmLabel: string
  /** Ricerca server-side: restituisce le opzioni per il testo digitato. */
  search: (text: string) => Promise<IPickable[]>
  /** Testo mostrato per ogni opzione. */
  optionLabel: (item: IPickable) => string
}>()

defineEmits([...useDialogPluginComponent.emits])

const { t } = useI18n()
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()
const selected = ref<IPickable | null>(null)
const options = ref<IPickable[]>([])
const loading = ref(false)

/**
 * Carica le opzioni per il testo digitato (chiamata dalla q-select).
 *
 * @param text - testo di ricerca
 * @param update - callback di Quasar per applicare le opzioni
 */
function onFilter(text: string, update: (fn: () => void) => void): void {
  loading.value = true
  props
    .search(text)
    .then((items) => update(() => (options.value = items)))
    .catch(() => update(() => (options.value = [])))
    .finally(() => (loading.value = false))
}
</script>
