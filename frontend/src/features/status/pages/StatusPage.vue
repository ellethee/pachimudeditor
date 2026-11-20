<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md">
      <h1 class="text-h5 q-my-none">{{ t('status.title') }}</h1>
      <q-space />
      <q-btn flat dense :icon="mdiRefresh" :label="t('status.reload')" :loading="loading" @click="load" />
    </div>

    <q-banner v-if="failed" rounded class="bg-negative text-white" data-testid="status-down">
      {{ t('status.down') }}
    </q-banner>
    <q-banner v-else-if="health && !health.database" rounded class="bg-warning text-dark" data-testid="status-db-down">
      {{ t('status.databaseDown') }}
    </q-banner>
    <q-banner v-else-if="health" rounded class="bg-positive text-white" data-testid="status-ok">
      {{ t('status.ok', { version: health.version }) }}
    </q-banner>

    <q-card v-if="worlds.length" flat bordered class="q-mt-md">
      <q-card-section class="text-h6">{{ t('status.worlds') }}</q-card-section>
      <q-list separator>
        <q-item v-for="world in worlds" :key="world.id">
          <q-item-section>
            <q-item-label>{{ world.name }}</q-item-label>
            <q-item-label caption>{{ world.id }} · {{ world.kind }}</q-item-label>
          </q-item-section>
          <q-item-section side class="row no-wrap items-center q-gutter-xs">
            <q-badge v-if="world.default" outline color="primary">{{ t('status.default') }}</q-badge>
            <q-badge v-if="world.capabilities.readOnly" outline color="orange">{{ t('status.readOnly') }}</q-badge>
          </q-item-section>
        </q-item>
      </q-list>
    </q-card>
  </div>
</template>

<script setup lang="ts">
/** Stato dell'editor: liveness del backend (`/api/health/`) e mondi configurati. */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiRefresh } from '@quasar/extras/mdi-v7'
import { ensureWorlds, useWorld } from '../../shared/helpers/world-state'
import { getHealth } from '../services/status-api'
import type { IHealth } from '../services/status-api'

const { t } = useI18n()
const { worlds } = useWorld()
const health = ref<IHealth | null>(null)
const failed = ref(false)
const loading = ref(false)

/** Interroga il backend. */
async function load(): Promise<void> {
  loading.value = true
  failed.value = false
  try {
    health.value = await getHealth()
  } catch {
    health.value = null
    failed.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void ensureWorlds()
  void load()
})
</script>
