<template>
  <div class="pachi-affects-field">
    <div class="text-caption text-grey-7 q-mb-xs">{{ label }}</div>
    <div v-for="row in rows" :key="row.uid" class="row q-col-gutter-sm items-start q-mb-xs">
      <div class="col-7">
        <q-select
          v-model="row.target"
          :options="filteredOptions"
          option-value="value"
          option-label="label"
          emit-value
          map-options
          outlined
          dense
          stack-label
          :use-input="freeText || filterable"
          :new-value-mode="freeText ? 'add-unique' : undefined"
          input-debounce="0"
          :label="t('objects.affects.target')"
          :readonly="readonly"
          :error="isDuplicate(row)"
          :error-message="t('objects.affects.duplicate')"
          @filter="filterOptions"
          @update:model-value="sync"
        />
      </div>
      <div class="col-3">
        <q-input
          v-model.number="row.bonus"
          type="number"
          outlined
          dense
          stack-label
          :label="t('objects.affects.bonus')"
          :readonly="readonly"
          @update:model-value="sync"
        />
      </div>
      <div class="col-2">
        <q-btn
          flat
          dense
          round
          color="negative"
          :icon="mdiDelete"
          :disable="readonly"
          :aria-label="t('objects.affects.remove')"
          @click="removeRow(row.uid)"
        >
          <q-tooltip>{{ t('objects.affects.remove') }}</q-tooltip>
        </q-btn>
      </div>
    </div>
    <div class="row items-center q-gutter-sm">
      <q-btn flat dense no-caps :icon="mdiPlus" :label="t('objects.affects.add')" :disable="readonly" @click="addRow" />
      <span v-if="rows.length === 0" class="text-caption text-grey">{{ t('objects.affects.empty') }}</span>
    </div>
    <div v-if="hint" class="text-caption text-grey-7 q-mt-xs">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
/**
 * Campo "affects" dell'oggetto (componente custom di `FieldsSection`): elenco di righe
 * bersaglio + bonus, con v-model `Record<string, number>` (bersaglio -> bonus). I bersagli arrivano
 * dal backend (`targetOptions`, enum `buffTarget` di `/api/meta/enums`); se l'elenco manca si
 * accetta testo libero. Le righe senza bersaglio o senza bonus numerico non vengono emesse.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiDelete, mdiPlus } from '@quasar/extras/mdi-v7'
import type { IBuffTargetOption } from '../types/objects'

/** Riga in modifica (`uid` stabile lato client, non inviato). */
interface IAffectRow {
  uid: number
  target: string | null
  bonus: number | null
}

const props = withDefaults(
  defineProps<{
    modelValue?: Record<string, number> | null
    label?: string
    hint?: string
    readonly?: boolean
    /** Bersagli ammessi (enum `buffTarget` del backend); vuoto = testo libero. */
    targetOptions?: IBuffTargetOption[]
  }>(),
  { modelValue: () => ({}), label: '', hint: '', readonly: false, targetOptions: () => [] },
)
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, number>] }>()

const { t } = useI18n()
let nextUid = 1

/**
 * Converte il dizionario in righe.
 *
 * @param value - dizionario bersaglio -> bonus
 */
function toRows(value: Record<string, number> | null | undefined): IAffectRow[] {
  return Object.entries(value ?? {}).map(([target, bonus]) => ({ uid: nextUid++, target, bonus }))
}

const rows = ref<IAffectRow[]>(toRows(props.modelValue))
/** Ultimo dizionario emesso/ricevuto, per ricostruire le righe solo su cambi esterni (es. reset). */
let lastSerialized = JSON.stringify(toDict())

/** Il bersaglio non è un'opzione nota: serve il testo libero. */
const freeText = computed(() => props.targetOptions.length === 0)
const filterable = computed(() => props.targetOptions.length > 8)
const filter = ref('')
const filteredOptions = computed<IBuffTargetOption[]>(() => {
  const needle = filter.value.trim().toLowerCase()
  return needle ? props.targetOptions.filter((o) => o.label.toLowerCase().includes(needle)) : props.targetOptions
})

/**
 * Filtra le opzioni per testo digitato.
 *
 * @param value - testo digitato
 * @param update - callback di QSelect
 */
function filterOptions(value: string, update: (fn: () => void) => void): void {
  update(() => {
    filter.value = value
  })
}

/** Costruisce il dizionario dalle righe valide. */
function toDict(): Record<string, number> {
  const out: Record<string, number> = {}
  for (const row of rows.value) {
    const target = row.target?.trim()
    if (target && typeof row.bonus === 'number' && Number.isFinite(row.bonus)) out[target] = row.bonus
  }
  return out
}

/**
 * Il bersaglio compare in più righe (l'ultima prevale nel dizionario).
 *
 * @param row - riga da controllare
 */
function isDuplicate(row: IAffectRow): boolean {
  return !!row.target && rows.value.some((other) => other.uid !== row.uid && other.target === row.target)
}

/** Emette il dizionario aggiornato. */
function sync(): void {
  const dict = toDict()
  lastSerialized = JSON.stringify(dict)
  emit('update:modelValue', dict)
}

/** Aggiunge una riga vuota. */
function addRow(): void {
  rows.value.push({ uid: nextUid++, target: null, bonus: 0 })
}

/**
 * Rimuove una riga.
 *
 * @param uid - identificatore locale della riga
 */
function removeRow(uid: number): void {
  rows.value = rows.value.filter((row) => row.uid !== uid)
  sync()
}

watch(
  () => props.modelValue,
  (value) => {
    if (JSON.stringify(value ?? {}) !== lastSerialized) {
      rows.value = toRows(value)
      lastSerialized = JSON.stringify(toDict())
    }
  },
  { deep: true },
)
</script>
