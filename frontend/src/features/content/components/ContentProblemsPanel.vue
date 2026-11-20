<template>
  <q-card v-if="issues.length > 0" flat bordered data-testid="content-problems">
    <q-card-section class="row items-center q-py-sm">
      <q-icon :name="errors > 0 ? mdiAlertCircle : mdiAlert" :color="errors > 0 ? 'negative' : 'warning'" size="sm" class="q-mr-sm" />
      <div class="text-subtitle2">{{ t('content.problems.title', { errors, warnings }) }}</div>
    </q-card-section>
    <q-separator />
    <q-list dense separator style="max-height: 280px; overflow: auto">
      <q-item v-for="(issue, i) in issues" :key="i" data-testid="content-problem">
        <q-item-section avatar>
          <q-badge :color="issue.severity === 'error' ? 'negative' : 'warning'" :text-color="issue.severity === 'error' ? 'white' : 'dark'" :label="issue.code" />
        </q-item-section>
        <q-item-section>
          <q-item-label>{{ issue.message }}</q-item-label>
          <q-item-label v-if="issue.file" caption style="font-family: monospace">{{ issue.file }}{{ issue.line ? `:${issue.line}` : '' }}</q-item-label>
        </q-item-section>
      </q-item>
    </q-list>
  </q-card>
</template>

<script setup lang="ts">
/** Pannello dei problemi dei contenuti (gravità, codice, messaggio, file e riga) dell'ultimo controllo del gioco. */
import { useI18n } from 'vue-i18n'
import { mdiAlert, mdiAlertCircle } from '@quasar/extras/mdi-v7'
import { useContentLive } from '../composables/use-content-live'

const { t } = useI18n()
const { issues, errors, warnings } = useContentLive()
</script>
