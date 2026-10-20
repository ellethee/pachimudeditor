<template>
  <q-banner dense inline-actions class="text-negative" data-testid="table-error">
    <template #avatar><q-icon :name="mdiAlertCircleOutline" color="negative" /></template>
    {{ message }}
    <template #action>
      <q-btn flat dense color="primary" :label="t('common.retry')" @click="retry" />
    </template>
  </q-banner>
</template>

<script setup lang="ts">
/**
 * Stato di errore del caricamento di una tabella (slot `error` di `PachiTable2`): mostra il messaggio
 * tradotto dell'errore invece dello `statusText` inglese del server, con il pulsante "Riprova".
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiAlertCircleOutline } from '@quasar/extras/mdi-v7'
import { describeHttpError } from '../helpers/http-errors'

const props = defineProps<{
  /** Errore del caricamento (slot `error`). */
  error: unknown
  /** Ripete il caricamento (slot `error`). */
  retry: () => unknown
}>()

const { t } = useI18n()
const message = ref('')

watch(
  () => props.error,
  async (error) => {
    message.value = await describeHttpError(error)
  },
  { immediate: true },
)
</script>
