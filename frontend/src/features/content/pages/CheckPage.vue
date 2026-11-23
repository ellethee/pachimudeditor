<template>
  <div class="q-pa-md column q-gutter-y-md">
    <div class="row items-center q-gutter-sm">
      <q-btn
        v-if="canValidate"
        color="primary"
        no-caps
        :icon="mdiClipboardCheckOutline"
        :label="t('content.live.validate')"
        :loading="busy"
        data-testid="check-run"
        @click="validate"
      />
      <q-toggle v-model="strict" :label="t('content.check.strict')" data-testid="check-strict">
        <q-tooltip>{{ t('content.check.strictHint') }}</q-tooltip>
      </q-toggle>
      <q-select
        v-if="zoneOptions.length > 1"
        v-model="zoneId"
        dense
        outlined
        emit-value
        map-options
        :options="zoneOptions"
        :label="t('content.check.zone')"
        style="min-width: 220px"
        data-testid="check-zone"
      />
      <q-badge v-if="checked && errors === 0 && warnings === 0" color="positive" :label="t('content.live.allOk')" data-testid="content-all-ok" />
    </div>
    <div v-if="!canValidate" class="text-caption text-grey-8" data-testid="check-off">{{ t('content.check.noChannel') }}</div>
    <div v-else-if="!checked" class="text-caption text-grey-8" data-testid="check-empty">{{ t('content.check.empty') }}</div>
    <content-problems-panel grouped :zone-id="zoneId" />
  </div>
</template>

<script setup lang="ts">
/**
 * Controllo dei contenuti: il gioco rilegge tutti i file come li carica (`content.validate`, anche in versione severa) e i problemi
 * si vedono raggruppati per codice, ognuno con la sua spiegazione; un clic apre la stanza, il mob, l'oggetto, i reset o la zona.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiClipboardCheckOutline } from '@quasar/extras/mdi-v7'
import { listZones } from '../../mobs/services/mobs-api'
import type { IZoneRef } from '../../mobs/types/mobs'
import ContentProblemsPanel from '../components/ContentProblemsPanel.vue'
import { useContentLive } from '../composables/use-content-live'

const { t } = useI18n()
const { targets, strict, checked, busy, errors, warnings, canValidate, validate, refreshStatus } = useContentLive()

const zones = ref<IZoneRef[]>([])
const zoneId = ref<number | null>(null)

/** Le zone che hanno almeno un problema, più «Tutte le zone». */
const zoneOptions = computed(() => {
  const withIssues = new Set(targets.value.map((x) => x?.zoneId).filter((z): z is number => z != null))
  return [
    { label: t('content.check.allZones'), value: null },
    ...zones.value.filter((z) => withIssues.has(z.vnum)).map((z) => ({ label: `${z.name} (${z.vnum})`, value: z.vnum })),
  ]
})

onMounted(async () => {
  void refreshStatus()
  try {
    zones.value = await listZones()
  } catch {
    zones.value = []
  }
})
</script>
