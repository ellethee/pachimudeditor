<template>
  <q-table
    flat
    bordered
    dense
    row-key="id"
    :rows="rows"
    :columns="columns"
    :loading="loading"
    :filter="filter"
    :pagination="{ rowsPerPage: 15 }"
    :rows-per-page-options="[15, 30, 0]"
    :no-data-label="t('content.empty')"
    :data-testid="testid"
    @row-click="(_e: Event, row: IListRow) => emit('select', row.id)"
  >
    <template #top>
      <q-btn color="primary" no-caps :icon="mdiPlus" :label="createLabel" :disable="readOnly" data-testid="item-create" @click="emit('create')" />
      <q-space />
      <q-input v-model="filter" dense outlined clearable :placeholder="t('content.search')" style="min-width: 160px">
        <template #prepend><q-icon :name="mdiMagnify" /></template>
      </q-input>
    </template>
    <template #body="{ row }">
      <q-tr :class="{ 'bg-blue-1': row.id === selected }" class="cursor-pointer" :props="{ row }" data-testid="item-row" @click="emit('select', row.id)">
        <q-td key="id">{{ row.id }}</q-td>
        <q-td key="info">{{ row.info }}</q-td>
        <q-td key="layer" class="text-right" auto-width>
          <q-badge v-if="row.error" color="negative" :label="t('content.status.invalid')"><q-tooltip>{{ row.error }}</q-tooltip></q-badge>
          <q-badge v-else-if="row.layer === 'user'" color="primary" outline :label="t('content.layer.user')" />
          <q-badge v-else color="grey" outline :label="t('content.layer.base')" />
        </q-td>
      </q-tr>
    </template>
  </q-table>
</template>

<script setup lang="ts">
/** Elenco di elementi a strati (skill, social): id, una riga di sintesi e lo strato (modificato qui / di serie). */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { QTableColumn } from 'quasar'
import { mdiMagnify, mdiPlus } from '@quasar/extras/mdi-v7'
import { useWorld } from '../../shared/helpers/world-state'
import type { ContentLayer } from '../types/content-files'

/** Una riga dell'elenco. */
export interface IListRow {
  id: string
  info: string
  layer: ContentLayer
  error?: string | null | undefined
}

defineProps<{ rows: IListRow[]; selected: string | null; loading: boolean; createLabel: string; testid: string }>()
const emit = defineEmits<{ select: [id: string]; create: [] }>()

const { t } = useI18n()
const { readOnly } = useWorld()
const filter = ref('')
const columns: QTableColumn<IListRow>[] = [
  { name: 'id', label: 'Id', field: 'id', align: 'left', sortable: true },
  { name: 'info', label: '', field: 'info', align: 'left' },
  { name: 'layer', label: '', field: 'layer', align: 'right' },
]
</script>
