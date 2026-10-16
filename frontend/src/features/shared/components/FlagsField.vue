<template>
  <q-select
    :model-value="modelValue"
    multiple
    use-chips
    use-input
    hide-dropdown-icon
    new-value-mode="add-unique"
    outlined
    dense
    stack-label
    :label="label"
    :hint="hint"
    :readonly="readonly"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>

<script setup lang="ts">
/**
 * Campo "flag": elenco libero di stringhe (digita e invio), usato come componente custom di
 * `FieldsSection`. Sostituisce il `type: 'select'` con `useInput`/`newValueMode` di
 * `@ilpachi/pachi-kit/fields`, in cui l'invio non crea il chip (la libreria registra
 * l'handler come `onNew-value`, che `emit('newValue')` di Quasar non trova).
 */
withDefaults(
  defineProps<{
    modelValue?: string[]
    label?: string
    hint?: string
    readonly?: boolean
  }>(),
  { modelValue: () => [], label: '', hint: '', readonly: false },
)

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
</script>
