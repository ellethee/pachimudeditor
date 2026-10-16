<template>
  <div class="q-pa-md">
    <h1 class="text-h5 q-mt-none q-mb-md">{{ t('instances.title') }}</h1>
    <q-tabs v-model="tab" align="left" dense active-color="primary" class="q-mb-md">
      <q-tab name="mob" :icon="mdiPaw" :label="t('instances.tabs.mobs')" />
      <q-tab name="object" :icon="mdiCubeOutline" :label="t('instances.tabs.objects')" />
    </q-tabs>
    <q-tab-panels v-model="tab" animated keep-alive>
      <q-tab-panel name="mob" class="q-pa-none">
        <instances-table kind="mob" />
      </q-tab-panel>
      <q-tab-panel name="object" class="q-pa-none">
        <instances-table kind="object" />
      </q-tab-panel>
    </q-tab-panels>
  </div>
</template>

<script setup lang="ts">
/** Pagina delle istanze vive: schede mob e oggetti. */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiCubeOutline, mdiPaw } from '@quasar/extras/mdi-v7'
import InstancesTable from '../components/InstancesTable.vue'
import type { InstanceKind } from '../types/instances'

const { t } = useI18n()
const tab = ref<InstanceKind>('mob')
</script>
