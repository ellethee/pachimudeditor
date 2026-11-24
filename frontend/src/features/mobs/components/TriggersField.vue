<template>
  <div class="column q-gutter-y-md" data-testid="triggers-field">
    <q-banner dense rounded class="bg-grey-3 text-dark" data-testid="triggers-hint">{{ t('mobs.triggers.hint') }}</q-banner>
    <div v-if="rows.length === 0" class="text-caption text-grey-8" data-testid="triggers-none">{{ t('mobs.triggers.none') }}</div>
    <q-card v-for="(row, index) in rows" :key="row.key" flat bordered data-testid="trigger-row">
      <q-card-section class="column q-gutter-y-sm">
        <div class="row q-col-gutter-md items-start">
          <q-select
            v-model="row.type"
            class="col-12 col-sm-5"
            outlined
            dense
            stack-label
            emit-value
            map-options
            :options="typeOptions"
            :label="t('mobs.triggers.type')"
            :readonly="readonly"
            data-testid="trigger-type"
            @update:model-value="changed"
          />
          <q-input
            v-model="row.argument"
            class="col-12 col-sm-5"
            outlined
            dense
            stack-label
            :label="t('mobs.triggers.argument')"
            :hint="t('mobs.triggers.argumentHint')"
            :readonly="readonly"
            data-testid="trigger-argument"
            @update:model-value="changed"
          />
          <q-input
            v-model.number="row.chance"
            class="col-8 col-sm-1"
            type="number"
            min="1"
            max="100"
            outlined
            dense
            stack-label
            :label="t('mobs.triggers.chance')"
            :readonly="readonly"
            :error="!validChance(row.chance)"
            :error-message="t('mobs.triggers.badChance')"
            data-testid="trigger-chance"
            @update:model-value="changed"
          />
          <q-btn v-if="!readonly" flat round dense color="negative" :icon="mdiDelete" :title="t('mobs.triggers.remove')" data-testid="trigger-remove" @click="remove(index)" />
        </div>
        <q-input
          v-model="row.actions"
          type="textarea"
          autogrow
          outlined
          dense
          stack-label
          :label="t('mobs.triggers.actions')"
          :readonly="readonly"
          :error="actionList(row).length === 0"
          :error-message="t('mobs.triggers.noActions')"
          input-style="font-family: monospace"
          data-testid="trigger-actions"
          @update:model-value="changed"
        />
        <q-banner
          v-for="(issue, i) in issuesOf(index)"
          :key="i"
          dense
          rounded
          :class="issue.severity === 'error' ? 'bg-negative text-white' : 'bg-warning text-black'"
          data-testid="trigger-issue"
        >
          <q-badge :color="issue.severity === 'error' ? 'white' : 'dark'" :text-color="issue.severity === 'error' ? 'negative' : 'white'" :label="issue.code" class="q-mr-sm" />
          {{ issue.message }}
          <q-tooltip v-if="te(`content.codes.${issue.code}`)">{{ t(`content.codes.${issue.code}`) }}</q-tooltip>
        </q-banner>
      </q-card-section>
    </q-card>
    <div v-if="!readonly">
      <q-btn flat no-caps color="primary" :icon="mdiPlus" :label="t('mobs.triggers.add')" data-testid="trigger-add" @click="add" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Scheda «Trigger» di un mob pachimud: il campo `triggers:` (`extra.triggers`), una lista di trigger con evento, argomento, probabilità e
 * azioni (un comando per riga). Sotto ogni trigger compaiono i problemi `trigger-command-unknown` / `trigger-variable-unknown` dell'ultimo
 * controllo dei contenuti (`content.validate`) che riguardano questo mob. Componente custom di `FieldsSection`.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiDelete, mdiPlus } from '@quasar/extras/mdi-v7'
import { useContentLive } from '../../content/composables/use-content-live'
import type { IContentIssue } from '../../content/types/content-files'
import { settledTriggers, triggerIndexOf, TRIGGER_TYPES } from '../helpers/triggers'
import type { ITrigger } from '../types/mobs'

const props = withDefaults(defineProps<{ modelValue?: unknown; readonly?: boolean; mobVnum?: number | null }>(), { readonly: false, mobVnum: null })
const emit = defineEmits<{ 'update:modelValue': [value: ITrigger[]] }>()

const { t, te } = useI18n()
const { issues, targets } = useContentLive()

interface IRow {
  key: number
  type: string
  argument: string
  chance: number
  actions: string
}

let seq = 0
/** Le righe del form (le azioni come testo, una per riga). */
function toRows(value: unknown): IRow[] {
  return (Array.isArray(value) ? (value as ITrigger[]) : []).map((x) => ({
    key: seq++,
    type: x.type,
    argument: x.argument ?? '',
    chance: x.chance ?? 100,
    actions: (x.actions ?? []).join('\n'),
  }))
}

const rows = ref<IRow[]>(toRows(props.modelValue))
const typeOptions = computed(() => TRIGGER_TYPES.map((value) => ({ value, label: t(`mobs.triggers.types.${value}`) })))

/** Le azioni di una riga: righe non vuote, senza spazi ai bordi. */
function actionList(row: IRow): string[] {
  return row.actions.split('\n').map((s) => s.trim()).filter(Boolean)
}

/** `true` se la probabilità è un intero da 1 a 100. */
function validChance(value: unknown): boolean {
  return Number.isInteger(value) && (value as number) >= 1 && (value as number) <= 100
}

/** Il valore da salvare (campi nell'ordine del backend). */
function current(): ITrigger[] {
  return rows.value.map((r) => ({ type: r.type, argument: r.argument ?? '', chance: r.chance, actions: actionList(r) }) as ITrigger)
}

function changed(): void {
  emit('update:modelValue', current())
}

function add(): void {
  rows.value.push({ key: seq++, type: 'speech', argument: '', chance: 100, actions: '' })
  changed()
}

function remove(index: number): void {
  rows.value.splice(index, 1)
  changed()
}

// reset / ricarica del record: riallinea le righe se il valore esterno non coincide con quello corrente
watch(
  () => props.modelValue,
  (value) => {
    if (JSON.stringify(settledTriggers(value)) !== JSON.stringify(current())) rows.value = toRows(value)
  },
)

/** I problemi di trigger del mob, con l'indice del trigger. */
const mine = computed(() =>
  issues.value
    .map((issue, i) => ({ issue, target: targets.value[i] }))
    .filter((x) => x.issue.code.startsWith('trigger-') && x.target?.kind === 'mob' && x.target.vnum === props.mobVnum)
    .map((x) => ({ issue: x.issue, index: triggerIndexOf(x.issue.message) })),
)

/** I problemi del trigger `index` (0-based). */
function issuesOf(index: number): IContentIssue[] {
  return mine.value.filter((x) => x.index === index).map((x) => x.issue)
}
</script>
