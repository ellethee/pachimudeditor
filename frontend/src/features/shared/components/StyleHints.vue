<template>
  <q-banner v-if="warnings.length" dense rounded class="bg-amber-2 text-dark q-mb-md" data-testid="style-hints">
    <div class="text-weight-medium">{{ t('style.title') }}</div>
    <ul class="q-my-xs q-pl-md">
      <li v-for="w in warnings" :key="w" data-testid="style-hint">{{ w }}</li>
    </ul>
  </q-banner>
</template>

<script setup lang="ts">
/**
 * Consigli di stile (titolo, descrizioni, parole chiave) di una stanza, un mob o un oggetto, con le soglie del mondo
 * (`validate.style` del gioco). Non bloccano il salvataggio; senza le soglie (mondo senza questa funzione) non compare nulla.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getStyleLimits } from '../../content/services/content-files-api'
import type { IStyleLimits } from '../../content/types/content-files'
import { styleWarnings } from '../helpers/style-lint'
import type { IStyleRecord } from '../helpers/style-lint'

const props = defineProps<{
  kind: 'room' | 'mob' | 'object'
  /** La voce salvata (si aggiorna a ogni salvataggio). */
  record: IStyleRecord | null
}>()

const { t } = useI18n()
const limits = ref<IStyleLimits | null>(null)

const warnings = computed(() => (limits.value && props.record ? styleWarnings(props.kind, props.record, limits.value, t) : []))

onMounted(async () => {
  try {
    limits.value = await getStyleLimits()
  } catch {
    limits.value = null // mondo senza lint di stile: nessun consiglio
  }
})
</script>
