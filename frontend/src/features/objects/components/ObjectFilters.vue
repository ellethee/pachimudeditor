<template>
  <q-expansion-item
    v-model="open"
    class="object-filters q-mb-sm"
    dense
    dense-toggle
    header-class="text-subtitle2"
    :icon="mdiFilterVariant"
    :label="active ? t('objects.filters.titleActive', { count: active }) : t('objects.filters.title')"
    data-test="object-filters"
  >
    <div class="row q-col-gutter-sm q-pa-sm">
      <q-select
        v-model="types"
        class="col-12 col-sm-6 col-md-4"
        :options="typeOptions"
        option-value="value"
        option-label="label"
        emit-value
        map-options
        multiple
        use-chips
        dense
        outlined
        clearable
        :label="t('objects.filters.types')"
      />
      <q-select
        v-model="wear"
        class="col-12 col-sm-6 col-md-4"
        v-bind="flagSelect"
        :options="shown.wear"
        :label="t('objects.filters.wear')"
        @filter="(val: string, update: UpdateFn) => filterNames(val, update, wearNames, 'wear')"
      />
      <q-select
        v-model="extra"
        class="col-12 col-sm-6 col-md-4"
        v-bind="flagSelect"
        :options="shown.extra"
        :label="t('objects.filters.extra')"
        @filter="(val: string, update: UpdateFn) => filterNames(val, update, extraNames, 'extra')"
      />
      <div v-for="key in RANGE_KEYS" :key="key" class="col-6 col-sm-3 col-md-2">
        <div class="row q-col-gutter-xs no-wrap">
          <q-input
            :model-value="range(key).min"
            class="col"
            type="number"
            dense
            outlined
            debounce="400"
            :error="invalid(key)"
            :label="t('objects.filters.min', { field: fieldLabel(key) })"
            @update:model-value="(v) => setRange(key, 'min', v)"
          />
          <q-input
            :model-value="range(key).max"
            class="col"
            type="number"
            dense
            outlined
            debounce="400"
            :error="invalid(key)"
            :error-message="t('objects.filters.rangeInvalid')"
            :label="t('objects.filters.max', { field: fieldLabel(key) })"
            @update:model-value="(v) => setRange(key, 'max', v)"
          />
        </div>
      </div>
      <q-select
        v-if="applyNames.length"
        v-model="affect"
        class="col-12 col-sm-6 col-md-4"
        :options="shown.apply"
        use-input
        input-debounce="0"
        dense
        outlined
        clearable
        :label="t('objects.filters.affect')"
        @filter="(val: string, update: UpdateFn) => filterNames(val, update, applyNames, 'apply')"
      />
      <q-input
        v-else
        v-model="affect"
        class="col-12 col-sm-6 col-md-4"
        dense
        outlined
        clearable
        debounce="400"
        :label="t('objects.filters.affect')"
      />
      <q-input
        :model-value="modelValue.minAffect"
        class="col-6 col-sm-3 col-md-2"
        type="number"
        dense
        outlined
        debounce="400"
        :disable="!modelValue.affect"
        :label="t('objects.filters.minAffect')"
        @update:model-value="(v) => emitWith({ minAffect: toInt(v) })"
      />
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
      :remove-aria-label="t('objects.filters.remove', { filter: chip.label })"
      @remove="chip.clear()"
    >
      {{ chip.label }}
    </q-chip>
    <q-btn flat dense no-caps color="primary" :label="t('objects.filters.reset')" @click="emit('update:modelValue', emptyFilters())" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiFilterVariant } from '@quasar/extras/mdi-v7'
import type { IEnumOption } from '../types/objects'
import { RANGE_KEYS, activeCount, emptyFilters, rangeInvalid } from '../helpers/list-query'
import type { IObjectFilters, IRange, RangeKey } from '../helpers/list-query'

/** Funzione `update` del filtro di un q-select. */
type UpdateFn = (callback: () => void) => void

const props = defineProps<{
  modelValue: IObjectFilters
  /** Opzioni del tipo oggetto (`/api/meta/enums`). */
  typeOptions: IEnumOption[]
  /** Nomi noti dei flag di indossabilità (vuoto: inserimento libero). */
  wearNames: string[]
  /** Nomi noti dei flag extra (vuoto: inserimento libero). */
  extraNames: string[]
  /** Nomi noti degli apply degli affect (vuoto: inserimento libero). */
  applyNames: string[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: IObjectFilters] }>()

const { t } = useI18n()
/** Chiusa di default (si apre se ci sono già filtri attivi, es. ripristinati dall'URL). */
const open = ref(activeCount(props.modelValue) > 0)
/** Opzioni mostrate dai select con inserimento (filtrate dal testo digitato). */
const shown = ref<Record<'wear' | 'extra' | 'apply', string[]>>({
  wear: [...props.wearNames],
  extra: [...props.extraNames],
  apply: [...props.applyNames],
})

/** Proprietà comuni dei selettori di flag (multipli, con inserimento libero se l'elenco non è noto). */
const flagSelect = {
  multiple: true,
  'use-input': true,
  'use-chips': true,
  'new-value-mode': 'add-unique',
  'input-debounce': 0,
  dense: true,
  outlined: true,
  clearable: true,
}

const active = computed(() => activeCount(props.modelValue))

/**
 * Emette i filtri con le modifiche indicate.
 *
 * @param patch - campi da cambiare
 */
function emitWith(patch: Partial<IObjectFilters>): void {
  emit('update:modelValue', { ...props.modelValue, ...patch })
}

/** Binding di un campo dei filtri; `null` (clear dei select) diventa il valore vuoto. */
function bind<K extends 'types' | 'wear' | 'extra' | 'affect'>(key: K, empty: IObjectFilters[K]) {
  return computed<IObjectFilters[K]>({
    get: () => props.modelValue[key],
    set: (value) => emitWith({ [key]: value ?? empty } as Partial<IObjectFilters>),
  })
}
const types = bind('types', [])
const wear = bind('wear', [])
const extra = bind('extra', [])
const affect = bind('affect', '')

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
function range(key: RangeKey): IRange {
  return props.modelValue.ranges[key]
}

/** `true` se min > max. */
function invalid(key: RangeKey): boolean {
  return rangeInvalid(range(key))
}

/**
 * Imposta un estremo di un intervallo.
 *
 * @param key - campo
 * @param bound - estremo
 * @param value - valore digitato
 */
function setRange(key: RangeKey, bound: 'min' | 'max', value: string | number | null): void {
  emitWith({ ranges: { ...props.modelValue.ranges, [key]: { ...range(key), [bound]: toInt(value) } } })
}

/**
 * Etichetta (breve) di un campo numerico.
 *
 * @param key - campo
 */
function fieldLabel(key: RangeKey): string {
  return t(`objects.fields.${key}Short`)
}

/**
 * Filtra le opzioni di un select con inserimento (sottostringa senza maiuscole).
 *
 * @param val - testo digitato
 * @param update - callback di Quasar
 * @param all - tutte le opzioni
 * @param target - elenco da aggiornare
 */
function filterNames(val: string, update: UpdateFn, all: string[], target: 'wear' | 'extra' | 'apply'): void {
  update(() => {
    const needle = val.toLowerCase()
    shown.value[target] = needle ? all.filter((name) => name.toLowerCase().includes(needle)) : [...all]
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
  if (f.types.length) {
    const names = f.types.map((v) => props.typeOptions.find((o) => o.value === v)?.label ?? String(v))
    out.push({ id: 'types', label: `${t('objects.filters.types')}: ${names.join(', ')}`, clear: () => emitWith({ types: [] }) })
  }
  if (f.wear.length)
    out.push({ id: 'wear', label: `${t('objects.filters.wear')}: ${f.wear.join(', ')}`, clear: () => emitWith({ wear: [] }) })
  if (f.extra.length)
    out.push({ id: 'extra', label: `${t('objects.filters.extra')}: ${f.extra.join(', ')}`, clear: () => emitWith({ extra: [] }) })
  if (f.affect) {
    const min = f.minAffect !== undefined ? ` ≥ ${f.minAffect}` : ''
    out.push({
      id: 'affect',
      label: `${t('objects.filters.affect')}: ${f.affect}${min}`,
      clear: () => emitWith({ affect: '', minAffect: undefined }),
    })
  }
  for (const key of RANGE_KEYS) {
    const { min, max } = f.ranges[key]
    if (min === undefined && max === undefined) continue
    const bounds = `${min ?? ''}…${max ?? ''}`
    out.push({
      id: key,
      label: `${t(`objects.columns.${key}`)}: ${bounds}`,
      clear: () => emitWith({ ranges: { ...f.ranges, [key]: {} } }),
    })
  }
  return out
})
</script>
