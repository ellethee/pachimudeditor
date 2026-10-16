<template>
  <q-select
    :model-value="modelValue"
    :options="options"
    :label="label"
    :hint="hint"
    :rules="rules"
    :disable="disable"
    :clearable="clearable"
    :loading="loading"
    use-input
    input-debounce="250"
    emit-value
    map-options
    outlined
    dense
    @filter="onFilter"
    @update:model-value="(value: number | null) => emit('update:modelValue', value ?? null)"
  >
    <template #no-option>
      <q-item>
        <q-item-section class="text-grey">{{ t('instances.picker.noResults') }}</q-item-section>
      </q-item>
    </template>
  </q-select>
</template>

<script setup lang="ts">
/**
 * Select con ricerca lato server su un valore numerico (id). Il chiamante fornisce `fetcher` (opzioni per
 * un testo digitato) e `resolver` (etichetta di un id già selezionato, ad esempio in modifica).
 */
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { IRemoteOption } from '../types/instances'

const props = defineProps<{
  modelValue: number | null | undefined
  label: string
  /** Opzioni che corrispondono al testo digitato. */
  fetcher: (term: string) => Promise<IRemoteOption[]>
  /** Opzione di un id (per mostrare l'etichetta del valore corrente); `null` se non esiste. */
  resolver: (id: number) => Promise<IRemoteOption | null>
  hint?: string | undefined
  rules?: ((value: unknown) => boolean | string)[] | undefined
  disable?: boolean | undefined
  clearable?: boolean | undefined
}>()
const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

const { t } = useI18n()
const options = ref<IRemoteOption[]>([])
const loading = ref(false)

/** Aggiunge `option` alle opzioni se non presente (così il valore selezionato resta etichettato). */
function ensureOption(option: IRemoteOption | null): void {
  if (option && !options.value.some((o) => o.value === option.value)) {
    options.value = [option, ...options.value]
  }
}

/** Carica l'etichetta del valore corrente quando non è tra le opzioni. */
async function resolveCurrent(): Promise<void> {
  const id = props.modelValue
  if (id === null || id === undefined || options.value.some((o) => o.value === id)) return
  try {
    ensureOption(await props.resolver(id))
  } catch {
    // l'id resta visibile come numero
  }
}

/**
 * Gestore del filtro di QSelect: cerca lato server e aggiorna le opzioni.
 *
 * @param term - testo digitato
 * @param update - callback di QSelect per applicare le opzioni
 */
async function onFilter(term: string, update: (fn: () => void) => void): Promise<void> {
  loading.value = true
  try {
    const found = await props.fetcher(term)
    update(() => {
      options.value = found
      if (props.modelValue !== null && props.modelValue !== undefined) {
        const current = options.value.find((o) => o.value === props.modelValue)
        if (!current) void resolveCurrent()
      }
    })
  } catch {
    update(() => undefined)
  } finally {
    loading.value = false
  }
}

onMounted(resolveCurrent)
watch(() => props.modelValue, resolveCurrent)
</script>
