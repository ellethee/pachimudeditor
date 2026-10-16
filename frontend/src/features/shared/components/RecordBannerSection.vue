<template>
  <q-banner
    rounded
    :class="corrupted ? 'bg-negative text-white' : 'bg-warning text-black'"
    :data-test="corrupted ? 'record-corrupted' : 'record-warning'"
  >
    <div class="text-weight-medium">{{ corrupted ? t('worlds.corrupted') : t('worlds.warning') }}</div>
    <div v-if="message" class="q-mt-xs">{{ message }}</div>
  </q-banner>
</template>

<script setup lang="ts">
/**
 * Sezione di `PachiEditDialog` con un banner d'avviso del record (`extra.corrupted` / `extra.warning`
 * dichiarati dall'adapter). Non ha stato proprio: espone solo il contratto minimo delle sezioni.
 */
import { useI18n } from 'vue-i18n'

defineProps<{
  /** Record non interpretabile: il form è in sola lettura. */
  corrupted: boolean
  /** Motivo riportato dall'adapter. */
  message: string
  /** Richiesto dal contratto delle sezioni; non usato. */
  initialValue?: unknown
}>()

const { t } = useI18n()

defineExpose({
  reset: () => undefined,
  commit: () => undefined,
  getResults: () => ({}),
  hasChanges: () => false,
})
</script>
