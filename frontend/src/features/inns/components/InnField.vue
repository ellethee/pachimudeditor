<template>
  <div class="column q-gutter-y-sm" data-testid="inn-field">
    <q-toggle :model-value="!!modelValue" :disable="readonly" :label="t('inns.isInnkeeper')" data-testid="inn-toggle" @update:model-value="emit('update:modelValue', $event)" />
    <q-banner dense rounded class="bg-grey-3 text-dark" data-testid="inn-hint">{{ t('inns.hint') }}</q-banner>
  </div>
</template>

<script setup lang="ts">
/** Flag `receptionist` del mob con la spiegazione di cosa fa (campo personalizzato di `FieldsSection`). */
import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{ modelValue?: unknown; readonly?: boolean }>(), { readonly: false })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const { t } = useI18n()
</script>
