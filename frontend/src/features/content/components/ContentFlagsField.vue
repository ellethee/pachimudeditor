<template>
  <q-select
    :model-value="modelValue"
    :options="options"
    multiple
    use-chips
    use-input
    input-debounce="0"
    outlined
    dense
    stack-label
    :label="label"
    :hint="hint"
    :readonly="readonly"
    @filter="onFilter"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>

<script setup lang="ts">
/**
 * Selezione multipla di valori testuali tra un elenco ammesso (flag di razza, caratteristiche), con filtro.
 * Componente custom di `FieldsSection`: riceve `v-model` e le altre chiavi del campo come prop.
 */
import { ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string[] | null
    /** Valori ammessi. */
    choices?: string[]
    label?: string
    hint?: string
    readonly?: boolean
  }>(),
  { modelValue: () => [], choices: () => [], label: '', hint: '', readonly: false },
)

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

const options = ref<string[]>(props.choices)
watch(
  () => props.choices,
  (value) => (options.value = value),
)

/**
 * Filtra le opzioni in base al testo digitato.
 * @param value testo digitato
 * @param update callback di Quasar per aggiornare l'elenco
 */
function onFilter(value: string, update: (fn: () => void) => void): void {
  update(() => {
    const needle = value.trim().toLowerCase()
    options.value = needle ? props.choices.filter((c) => c.toLowerCase().includes(needle)) : props.choices
  })
}
</script>
