<template>
  <q-input
    ref="input"
    :model-value="modelValue"
    type="number"
    :loading="loading"
    @update:model-value="onInput"
  >
    <template v-if="!$attrs.disable && zoneId" #append>
      <q-btn dense flat round :icon="mdiAutoFix" @click="suggest">
        <q-tooltip>{{ t('mobs.vnumSuggest') }}</q-tooltip>
      </q-btn>
    </template>
  </q-input>
</template>

<script setup lang="ts">
/**
 * Campo vnum custom per `FieldsSection`: input numerico con pulsante che propone il prossimo vnum
 * libero della zona. Riceve `v-model` e gli altri attributi del campo (label, rules, disable, ...).
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { QInput } from 'quasar'
import { mdiAutoFix } from '@quasar/extras/mdi-v7'
import { nextMobVnum } from '../services/mobs-api'

defineOptions({ inheritAttrs: true })

const props = defineProps<{
  modelValue?: number | null | undefined
  /** Zona di cui proporre il vnum. */
  zoneId?: number | undefined
}>()
const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

const { t } = useI18n()
const input = ref<InstanceType<typeof QInput> | null>(null)
const loading = ref(false)

/** Converte il testo digitato in numero (o `null` se vuoto/non numerico). */
function onInput(value: string | number | null): void {
  const n = value === null || value === '' ? NaN : Number(value)
  emit('update:modelValue', Number.isNaN(n) ? null : n)
}

/** Chiede al backend il prossimo vnum libero della zona e lo imposta. */
async function suggest(): Promise<void> {
  if (!props.zoneId) return
  loading.value = true
  try {
    emit('update:modelValue', await nextMobVnum(props.zoneId))
  } finally {
    loading.value = false
  }
}

/** Valida l'input interno (mostra l'errore anche senza interazione). */
async function validate(): Promise<boolean> {
  return (await input.value?.validate()) ?? true
}

defineExpose({ validate })
</script>
