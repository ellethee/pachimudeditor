<template>
  <q-banner
    v-if="status"
    rounded
    dense
    :class="pending ? 'bg-warning text-dark' : 'bg-blue-1 text-dark'"
    data-testid="restart-banner"
  >
    <template #avatar>
      <q-icon :name="pending ? mdiRestartAlert : mdiInformationOutline" />
    </template>
    <div class="text-weight-medium">{{ t('content.restart.title') }}</div>
    <div>{{ pending ? t('content.restart.pending', { when }) : t('content.restart.info') }}</div>
    <template v-if="pending" #action>
      <q-btn flat dense no-caps :label="t('content.restart.acknowledge')" @click="acknowledge" />
    </template>
  </q-banner>
</template>

<script setup lang="ts">
/**
 * Avviso "riavvio necessario": il game server legge razze e classi (YAML) solo all'avvio, quindi ogni
 * modifica fatta qui ha effetto dopo un suo riavvio. Se dopo l'ultimo "ho riavviato" qualche file è
 * cambiato, il banner passa a giallo; l'utente può confermare di aver riavviato (stato nel browser).
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiInformationOutline, mdiRestartAlert } from '@quasar/extras/mdi-v7'
import { getContentStatus } from '../services/content-api'
import type { IContentStatus } from '../types/content'

const ACK_KEY = 'content.restartAcknowledged'

const { t } = useI18n()
const status = ref<IContentStatus | null>(null)
const acknowledged = ref(0)

/**
 * Legge l'ultimo istante confermato dal browser (assente o illeggibile -> 0).
 */
function readAck(): number {
  try {
    return Number(window.localStorage.getItem(ACK_KEY)) || 0
  } catch {
    return 0
  }
}

/** Vero se esiste una modifica più recente dell'ultima conferma. */
const pending = computed(() => !!status.value?.lastModified && status.value.lastModified > acknowledged.value)

/** Data dell'ultima modifica, formattata. */
const when = computed(() => (status.value?.lastModified ? new Date(status.value.lastModified * 1000).toLocaleString() : ''))

/** Ricarica lo stato dal backend (da chiamare dopo ogni salvataggio). */
async function refresh(): Promise<void> {
  try {
    status.value = await getContentStatus()
  } catch {
    status.value = null
  }
}

/** Segna come riavviato il game server: nasconde l'avviso fino alla prossima modifica. */
function acknowledge(): void {
  acknowledged.value = status.value?.lastModified ?? 0
  try {
    window.localStorage.setItem(ACK_KEY, String(acknowledged.value))
  } catch {
    // storage non disponibile: la conferma vale solo per questa sessione
  }
}

onMounted(() => {
  acknowledged.value = readAck()
  void refresh()
})

defineExpose({ refresh })
</script>
