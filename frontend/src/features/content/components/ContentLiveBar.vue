<template>
  <div class="column q-gutter-y-sm" data-testid="content-live-bar">
    <div class="row items-center q-gutter-sm">
      <q-btn
        v-if="canValidate"
        outline
        no-caps
        color="primary"
        :icon="mdiClipboardCheckOutline"
        :label="t('content.live.validate')"
        :loading="busy"
        data-testid="content-validate"
        @click="validate"
      />
      <q-btn
        v-if="canReload"
        outline
        no-caps
        color="primary"
        :icon="mdiReload"
        :label="t('content.live.reload')"
        :loading="busy"
        data-testid="content-reload"
        @click="reloadNow"
      />
      <span v-if="!canValidate && !canReload" class="text-caption text-grey-8" data-testid="content-live-off">
        {{ t('content.live.off') }}
      </span>
      <q-badge v-if="checked && errors === 0 && warnings === 0" color="positive" :label="t('content.live.allOk')" data-testid="content-all-ok" />
    </div>
    <content-problems-panel />
  </div>
</template>

<script setup lang="ts">
/**
 * Barra del canale live dei contenuti: «Controlla i file» (`content.validate`) e «Ricarica nel gioco» (`content.reload`) per il tipo di
 * contenuto della pagina, più il pannello dei problemi. I pulsanti compaiono solo se il canale è connesso e il gioco dichiara i comandi.
 */
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiClipboardCheckOutline, mdiReload } from '@quasar/extras/mdi-v7'
import ContentProblemsPanel from './ContentProblemsPanel.vue'
import { useContentLive } from '../composables/use-content-live'
import type { ReloadKind } from '../types/content-files'

const props = defineProps<{
  /** Cosa rilegge «Ricarica nel gioco» in questa pagina. */
  kind: ReloadKind
}>()

const { t } = useI18n()
const { busy, checked, errors, warnings, canValidate, canReload, validate, reload, refreshStatus } = useContentLive()

/** Ricarica nel gioco e, se riuscito, rilegge i problemi (restano gli avvisi). */
async function reloadNow(): Promise<void> {
  if (await reload(props.kind)) await validate()
}

onMounted(() => void refreshStatus())
defineExpose({ validate })
</script>
