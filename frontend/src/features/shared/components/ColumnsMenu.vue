<template>
  <q-btn flat round :icon="mdiTableColumn" :aria-label="t('listFilters.columns.button')" data-test="columns-menu">
    <q-tooltip>{{ t('listFilters.columns.button') }}</q-tooltip>
    <q-menu>
      <q-list dense style="min-width: 200px">
        <q-item-label header>{{ t('listFilters.columns.title') }}</q-item-label>
        <q-item v-for="name in names" :key="name" tag="label" v-ripple>
          <q-item-section side>
            <q-checkbox
              dense
              :model-value="modelValue.includes(name)"
              :disable="modelValue.length === 1 && modelValue.includes(name)"
              @update:model-value="(on: boolean) => emit('toggle', name, on)"
            />
          </q-item-section>
          <q-item-section>{{ labelOf(name) }}</q-item-section>
        </q-item>
        <q-separator />
        <q-item clickable v-close-popup @click="emit('reset')">
          <q-item-section>{{ t('listFilters.columns.reset') }}</q-item-section>
        </q-item>
      </q-list>
    </q-menu>
  </q-btn>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { mdiTableColumn } from '@quasar/extras/mdi-v7'

/** Menu per scegliere le colonne visibili di una tabella (la scelta la salva la pagina). */
defineProps<{
  /** Nomi delle colonne selezionabili, nell'ordine di visualizzazione. */
  names: string[]
  /** Nomi delle colonne visibili. */
  modelValue: string[]
  /** Etichetta (tradotta) di una colonna. */
  labelOf: (name: string) => string
}>()
const emit = defineEmits<{ toggle: [name: string, on: boolean]; reset: [] }>()
const { t } = useI18n()
</script>
