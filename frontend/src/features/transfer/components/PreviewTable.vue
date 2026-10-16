<template>
  <q-markup-table flat bordered dense separator="horizontal">
    <thead>
      <tr>
        <th class="text-left">{{ t('transfer.preview.kind') }}</th>
        <th class="text-right">{{ t('transfer.preview.create') }}</th>
        <th class="text-right">{{ t('transfer.preview.update') }}</th>
        <th class="text-right">{{ t('transfer.preview.unchanged') }}</th>
        <th class="text-right">{{ t('transfer.preview.kept') }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in rows" :key="row.key">
        <td>{{ t(`transfer.preview.kinds.${row.key}`) }}</td>
        <td class="text-right">{{ row.diff.create }}</td>
        <td class="text-right">{{ row.diff.update }}</td>
        <td class="text-right">{{ row.diff.unchanged }}</td>
        <td class="text-right">
          {{ row.diff.keptNotInFile.length }}
          <q-tooltip v-if="row.diff.keptNotInFile.length">{{ row.diff.keptNotInFile.join(', ') }}</q-tooltip>
        </td>
      </tr>
      <tr>
        <td>{{ t('transfer.preview.kinds.resets') }}</td>
        <td colspan="4" class="text-right">
          {{ t('transfer.preview.resetsSummary', { inFile: preview.resets.inFile, inDb: preview.resets.inDb }) }}
          <q-badge :color="preview.resets.changed ? 'warning' : 'grey'" text-color="dark" class="q-ml-sm" :label="t(preview.resets.changed ? 'transfer.preview.replaced' : 'transfer.preview.unchanged')" />
        </td>
      </tr>
    </tbody>
  </q-markup-table>
</template>

<script setup lang="ts">
/** Tabella di riepilogo dell'anteprima di import: creazioni/aggiornamenti per tipo di contenuto. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { IImportPreview, IKindDiff } from '../types/transfer'

const props = defineProps<{ preview: IImportPreview }>()
const { t } = useI18n()

/** Le tre righe per tipo, nell'ordine di visualizzazione. */
const rows = computed<{ key: 'rooms' | 'mobs' | 'objects'; diff: IKindDiff }[]>(() => [
  { key: 'rooms', diff: props.preview.rooms },
  { key: 'mobs', diff: props.preview.mobs },
  { key: 'objects', diff: props.preview.objects },
])
</script>
