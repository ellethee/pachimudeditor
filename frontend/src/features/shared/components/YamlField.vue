<template>
  <div>
    <div v-if="label" class="text-caption text-grey-7 q-mb-xs">{{ label }}</div>
    <code-editor :model-value="modelValue" language="yaml" :height="height" :readonly="readonly" :error="error" @update:model-value="emit('update:modelValue', $event)" />
    <div v-if="hint && !error" class="text-caption text-grey-7 q-mt-xs">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
/**
 * Campo YAML (CodeEditor) per `FieldsSection`/`PachiEditDialog`: testo `v-model` con etichetta e hint sopra/sotto l'editor.
 */
import CodeEditor from './CodeEditor.vue'

withDefaults(
  defineProps<{
    modelValue?: string
    label?: string
    hint?: string
    readonly?: boolean
    error?: string
    height?: string
  }>(),
  { modelValue: '', label: '', hint: '', readonly: false, error: '', height: '12em' },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
