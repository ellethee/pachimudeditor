<template>
  <div>
    <div class="text-subtitle1 q-mb-sm">{{ t('rooms.extras.title') }}</div>
    <div v-for="(extra, index) in state.rows" :key="extra.uid" class="row q-gutter-sm q-mb-sm items-start">
      <q-input v-model="extra.keywords" :label="t('rooms.extras.keywords')" class="col-4" dense outlined />
      <q-input
        v-model="extra.text"
        :label="t('rooms.extras.text')"
        type="textarea"
        autogrow
        class="col"
        dense
        outlined
      />
      <q-btn dense flat round :icon="mdiDelete" color="negative" @click="state.rows.splice(index, 1)">
        <q-tooltip>{{ t('rooms.extras.remove') }}</q-tooltip>
      </q-btn>
    </div>
    <q-btn flat :icon="mdiPlus" :label="t('rooms.extras.add')" @click="addRow" />
  </div>
</template>

<script setup lang="ts">
/**
 * Sezione di `PachiEditDialog`: elenco modificabile di extra description (parole chiave + testo).
 * Ogni riga ha un `uid` stabile lato client, usato dal salvataggio per distinguere righe nuove e esistenti.
 */
import { useI18n } from 'vue-i18n'
import { mdiDelete, mdiPlus } from '@quasar/extras/mdi-v7'
import { useSection } from '@ilpachi/pachi-kit/edit-dialog'
import type { IExtraRow } from '../types/rooms'

interface IExtrasState {
  rows: IExtraRow[]
}

const props = defineProps<{ initialValue?: IExtrasState }>()

const { t } = useI18n()
const { state, reset, commit, getResults, hasChanges } = useSection<IExtrasState>(
  { rows: [] },
  { initialValue: () => props.initialValue },
)

/** Aggiunge una riga vuota. */
function addRow(): void {
  state.value.rows.push({ uid: `new-${crypto.randomUUID()}`, keywords: '', text: '' })
}

defineExpose({ reset, commit, getResults, hasChanges: () => hasChanges.value })
</script>
