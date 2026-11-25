<template>
  <q-expansion-item
    v-model="open"
    class="list-filters q-mb-sm"
    dense
    dense-toggle
    header-class="text-subtitle2"
    :icon="mdiFilterVariant"
    :label="active ? t('listFilters.titleActive', { count: active }) : t('listFilters.title')"
    data-test="list-filters"
  >
    <div class="row q-col-gutter-sm q-pa-sm">
      <template v-for="control in shown" :key="control.key">
        <div v-if="control.kind === 'range'" class="col-12 col-sm-6 col-md-4 col-lg-3">
          <div class="row q-col-gutter-xs no-wrap">
            <q-input
              :model-value="rangeOf(control.key).min"
              class="col"
              type="number"
              dense
              outlined
              debounce="400"
              :error="invalid(control.key)"
              :label="t('listFilters.min', { field: control.short ?? control.label })"
              @update:model-value="(v) => setRange(control.key, 'min', v)"
            />
            <q-input
              :model-value="rangeOf(control.key).max"
              class="col"
              type="number"
              dense
              outlined
              debounce="400"
              :error="invalid(control.key)"
              :error-message="t('listFilters.rangeInvalid')"
              :label="t('listFilters.max', { field: control.short ?? control.label })"
              @update:model-value="(v) => setRange(control.key, 'max', v)"
            />
          </div>
        </div>
        <div v-else-if="control.kind === 'tri'" class="col-12 col-sm-6 col-md-4 row items-center no-wrap q-gutter-x-sm" :data-test="`tri-${control.key}`">
          <span class="text-caption ellipsis">{{ control.label }}</span>
          <q-btn-toggle
            :model-value="modelValue.texts[control.key] ?? ''"
            :options="triOptions"
            dense
            no-caps
            unelevated
            toggle-color="primary"
            @update:model-value="(v: string) => setText(control.key, v)"
          />
        </div>
        <q-input
          v-else-if="control.kind === 'text'"
          :model-value="modelValue.texts[control.key]"
          class="col-12 col-sm-6 col-md-4"
          dense
          outlined
          clearable
          debounce="400"
          :label="control.label"
          @update:model-value="(v) => setText(control.key, v)"
        />
        <q-select
          v-else
          :model-value="modelValue.lists[control.key]"
          class="col-12 col-sm-6 col-md-4"
          :options="optionsOf(control)"
          option-value="value"
          option-label="label"
          emit-value
          map-options
          multiple
          use-chips
          dense
          outlined
          clearable
          v-bind="control.free ? freeSelect : {}"
          :label="control.label"
          @filter="(val: string, update: UpdateFn) => filterOptions(val, update, control)"
          @update:model-value="(v: (string | number)[] | null) => setList(control.key, v)"
        />
      </template>
    </div>
  </q-expansion-item>
  <div v-if="chips.length" class="row items-center q-gutter-xs q-mb-sm" data-test="active-filters">
    <q-chip
      v-for="chip in chips"
      :key="chip.id"
      removable
      dense
      color="primary"
      text-color="white"
      :remove-aria-label="t('listFilters.remove', { filter: chip.label })"
      @remove="chip.clear()"
    >
      {{ chip.label }}
    </q-chip>
    <q-btn flat dense no-caps color="primary" :label="t('listFilters.reset')" @click="emit('update:modelValue', emptyFilters(controls))" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiFilterVariant } from '@quasar/extras/mdi-v7'
import { activeCount, emptyFilters, rangeInvalid } from '../helpers/list-filters'
import type { IFilterControl, IFilterOption, IListFilters, IRange } from '../helpers/list-filters'

/** Funzione `update` del filtro di un q-select. */
type UpdateFn = (callback: () => void) => void

/**
 * Barra dei filtri di una lista: elenchi (multi-selezione), testo e intervalli numerici in un pannello comprimibile
 * (chiuso di default su telefono), chip dei filtri attivi rimovibili e «azzera». I controlli li descrive la pagina.
 */
const props = defineProps<{ modelValue: IListFilters; controls: IFilterControl[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: IListFilters] }>()

const { t } = useI18n()
/** Opzioni mostrate dai select con inserimento libero (filtrate dal testo digitato). */
const typed = ref<Record<string, string>>({})

/** Opzioni del filtro sì/no: tutti (nessun filtro), sì, no. */
const triOptions = computed(() => [
  { label: t('listFilters.tri.all'), value: '' },
  { label: t('listFilters.tri.yes'), value: 'true' },
  { label: t('listFilters.tri.no'), value: 'false' },
])

/** Proprietà dei selettori con inserimento libero (nuovi valori accettati con Invio). */
const freeSelect = { 'use-input': true, 'new-value-mode': 'add-unique', 'input-debounce': 0 }

const shown = computed(() => props.controls.filter((control) => !control.hidden))
const active = computed(() => activeCount(shown.value, props.modelValue))
/** Chiusa di default (si apre se ci sono già filtri attivi, es. ripristinati dall'URL). */
const open = ref(active.value > 0)

/**
 * Emette i filtri con le modifiche indicate.
 *
 * @param patch - parti dello stato da cambiare
 */
function emitWith(patch: Partial<IListFilters>): void {
  emit('update:modelValue', { ...props.modelValue, ...patch })
}

/**
 * Intero da un valore di input (`undefined` se vuoto o non numerico).
 *
 * @param value - valore del q-input
 */
function toInt(value: string | number | null): number | undefined {
  if (value === null || value === '') return undefined
  const parsed = Number(value)
  return Number.isInteger(parsed) ? parsed : undefined
}

/** Intervallo corrente di un campo. */
function rangeOf(key: string): IRange {
  return props.modelValue.ranges[key] ?? {}
}

/** `true` se min > max. */
function invalid(key: string): boolean {
  return rangeInvalid(rangeOf(key))
}

/**
 * Imposta un estremo di un intervallo.
 *
 * @param key - chiave del filtro
 * @param bound - estremo
 * @param value - valore digitato
 */
function setRange(key: string, bound: 'min' | 'max', value: string | number | null): void {
  emitWith({ ranges: { ...props.modelValue.ranges, [key]: { ...rangeOf(key), [bound]: toInt(value) } } })
}

/**
 * Imposta il valore di un filtro di testo.
 *
 * @param key - chiave del filtro
 * @param value - testo (`null` dopo «clear»)
 */
function setText(key: string, value: string | number | null): void {
  emitWith({ texts: { ...props.modelValue.texts, [key]: value === null ? '' : String(value) } })
}

/**
 * Imposta i valori di un filtro a elenco (`null` dopo «clear»: vuoto).
 *
 * @param key - chiave del filtro
 * @param value - valori scelti
 */
function setList(key: string, value: (string | number)[] | null): void {
  emitWith({ lists: { ...props.modelValue.lists, [key]: value ?? [] } })
}

/** Opzioni da mostrare per un elenco (per quelli liberi, i valori digitati o già scelti sono sempre disponibili). */
function optionsOf(control: IFilterControl): IFilterOption[] {
  const all = control.options ?? []
  const needle = (typed.value[control.key] ?? '').toLowerCase()
  return needle ? all.filter((option) => option.label.toLowerCase().includes(needle)) : all
}

/**
 * Filtra le opzioni di un select con inserimento (sottostringa senza maiuscole).
 *
 * @param val - testo digitato
 * @param update - callback di Quasar
 * @param control - controllo
 */
function filterOptions(val: string, update: UpdateFn, control: IFilterControl): void {
  update(() => {
    typed.value = { ...typed.value, [control.key]: val }
  })
}

interface IChip {
  id: string
  label: string
  clear: () => void
}

/** Un chip per ogni filtro attivo, rimovibile singolarmente. */
const chips = computed<IChip[]>(() => {
  const f = props.modelValue
  const out: IChip[] = []
  for (const control of shown.value) {
    const { key, label } = control
    if (control.kind === 'list') {
      const values = f.lists[key] ?? []
      if (!values.length) continue
      const names = values.map((v) => control.options?.find((o) => o.value === v)?.label ?? String(v))
      out.push({ id: key, label: `${label}: ${names.join(', ')}`, clear: () => setList(key, []) })
    } else if (control.kind === 'text') {
      const text = (f.texts[key] ?? '').trim()
      if (text) out.push({ id: key, label: `${label}: ${text}`, clear: () => setText(key, '') })
    } else if (control.kind === 'tri') {
      const value = f.texts[key]
      if (value === 'true' || value === 'false') {
        out.push({ id: key, label: `${label}: ${t(value === 'true' ? 'listFilters.tri.yes' : 'listFilters.tri.no')}`, clear: () => setText(key, '') })
      }
    } else {
      const { min, max } = rangeOf(key)
      if (min === undefined && max === undefined) continue
      out.push({ id: key, label: `${label}: ${min ?? ''}…${max ?? ''}`, clear: () => emitWith({ ranges: { ...f.ranges, [key]: {} } }) })
    }
  }
  return out
})
</script>
