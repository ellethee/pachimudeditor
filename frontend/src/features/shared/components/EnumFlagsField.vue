<template>
  <q-select
    :model-value="modelValue"
    :options="shown"
    multiple
    use-chips
    use-input
    input-debounce="0"
    new-value-mode="add-unique"
    outlined
    dense
    stack-label
    :label="label"
    :hint="hint"
    :readonly="readonly"
    @filter="filter"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>

<script setup lang="ts">
/**
 * Campo "flag" con elenco di nomi noti (tabelle ROM di `/api/meta/enums`): si sceglie dall'elenco filtrabile;
 * un valore non in elenco si può comunque aggiungere con Invio (il backend risponde 422 se è sconosciuto).
 * Componente custom di `FieldsSection`, alternativa a `FlagsField` (testo libero) quando il descrittore del
 * campo dichiara un `enum`.
 */
import { ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string[]
    /** Nomi ammessi. */
    options?: string[]
    label?: string
    hint?: string
    readonly?: boolean
  }>(),
  { modelValue: () => [], options: () => [], label: '', hint: '', readonly: false },
)

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

const shown = ref<string[]>(props.options)
watch(
  () => props.options,
  (options) => (shown.value = options),
)

/**
 * Filtra le opzioni in base al testo digitato.
 *
 * @param text - testo digitato
 * @param update - callback di Quasar per applicare l'elenco filtrato
 */
function filter(text: string, update: (fn: () => void) => void): void {
  update(() => {
    const needle = text.toLowerCase()
    shown.value = props.options.filter((option) => option.toLowerCase().includes(needle))
  })
}
</script>
