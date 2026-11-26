<template>
  <div class="column q-gutter-y-md" data-testid="triggers-field">
    <q-banner dense rounded class="bg-grey-3 text-dark" data-testid="triggers-hint">{{ t(`triggers.hint.${owner}`) }}</q-banner>
    <div v-if="rows.length === 0" class="text-caption text-grey-8" data-testid="triggers-none">{{ t(`triggers.none.${owner}`) }}</div>
    <q-card v-for="(row, index) in rows" :key="row.key" flat bordered data-testid="trigger-row">
      <q-card-section class="column q-gutter-y-sm">
        <div class="row q-col-gutter-md items-start">
          <q-select
            v-model="row.type"
            class="col-12 col-sm-3"
            outlined
            dense
            stack-label
            emit-value
            map-options
            :options="typeOptions"
            :label="t('triggers.type')"
            :readonly="readonly"
            data-testid="trigger-type"
            @update:model-value="changed"
          />
          <q-input
            v-model="row.argument"
            class="col-12 col-sm-6"
            outlined
            dense
            stack-label
            :label="t('triggers.argument')"
            :hint="t(`triggers.argumentHints.${row.type}`, '')"
            :readonly="readonly"
            :error="!argumentOk(row)"
            :error-message="t('triggers.badArgument')"
            data-testid="trigger-argument"
            @update:model-value="changed"
          />
          <q-toggle
            v-if="(BLOCKABLE as readonly string[]).includes(row.type)"
            v-model="row.block"
            class="col-12"
            dense
            :label="t('triggers.block')"
            :disable="readonly"
            data-testid="trigger-block"
            @update:model-value="changed"
          />
          <q-input
            v-model.number="row.chance"
            class="col-8 col-sm-2"
            type="number"
            min="1"
            max="100"
            outlined
            dense
            stack-label
            :label="t('triggers.chance')"
            :readonly="readonly"
            :error="!validChance(row.chance)"
            :error-message="t('triggers.badChance')"
            data-testid="trigger-chance"
            @update:model-value="changed"
          />
          <q-btn v-if="!readonly" flat round dense color="negative" :icon="mdiDelete" :title="t('triggers.remove')" data-testid="trigger-remove" @click="remove(index)" />
        </div>
        <div class="text-caption text-grey-8">{{ t('triggers.actions') }}</div>
        <actions-editor
          v-model="row.actions"
          :owner="owner"
          :readonly="readonly"
          :races="races"
          :classes="classes"
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
      <q-btn flat no-caps color="primary" :icon="mdiPlus" :label="t(`triggers.add.${owner}`)" data-testid="trigger-add" @click="add" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Scheda «Trigger» di un mob o di una stanza e «Script» di un oggetto pachimud (`extra.triggers` / `extra.scripts`): una lista di
 * trigger con evento, argomento, probabilità e azioni (comandi e blocchi `if`/`else`, vedi `ActionsEditor`). Sotto ogni trigger
 * compaiono i problemi dell'ultimo controllo dei contenuti (`content.validate`) che riguardano quella voce. Componente custom di
 * `FieldsSection`.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiDelete, mdiPlus } from '@quasar/extras/mdi-v7'
import { useContentLive } from '../../content/composables/use-content-live'
import type { IContentIssue } from '../../content/types/content-files'
import { listClasses, listRaces } from '../../mobs/services/mobs-api'
import { argumentValid, BLOCKABLE, settledTriggers, triggerIndexOf, TRIGGER_TYPES } from '../helpers/triggers'
import type { ITrigger, TAction, TriggerOwner } from '../types/triggers'
import ActionsEditor from './ActionsEditor.vue'

const props = withDefaults(defineProps<{ modelValue?: unknown; readonly?: boolean; owner?: TriggerOwner; vnum?: number | null }>(), {
  readonly: false,
  owner: 'mob',
  vnum: null,
})
const emit = defineEmits<{ 'update:modelValue': [value: ITrigger[]] }>()

const { t, te } = useI18n()
const { issues, targets } = useContentLive()

interface IRow {
  key: number
  type: string
  argument: string
  block?: boolean
  chance: number
  actions: TAction[]
}

let seq = 0
/** Le righe del form. */
function toRows(value: unknown): IRow[] {
  return settledTriggers(value).map((x) => ({ key: seq++, ...x }))
}

const rows = ref<IRow[]>(toRows(props.modelValue))
const typeOptions = computed(() => TRIGGER_TYPES[props.owner].map((value) => ({ value, label: t(`triggers.types.${value}`) })))

/** Razze e classi del mondo, per i suggerimenti delle condizioni (senza cataloghi si scrive l'id a mano). */
const races = ref<{ id: string; name: string }[]>([])
const classes = ref<{ id: string; name: string }[]>([])
onMounted(async () => {
  if (props.readonly) return
  races.value = await listRaces().catch(() => [])
  classes.value = await listClasses().catch(() => [])
})

/** `true` se la probabilità è un intero da 1 a 100. */
function validChance(value: unknown): boolean {
  return Number.isInteger(value) && (value as number) >= 1 && (value as number) <= 100
}

/** `hitprcnt` e `bribe` vogliono un numero positivo (`hitprcnt` fino a 100). */
function argumentOk(row: IRow): boolean {
  if (!argumentValid(row.type, row.argument)) return false
  if (row.type !== 'hitprcnt' && row.type !== 'bribe') return true
  const text = row.argument.trim()
  return /^\d+$/.test(text) && Number(text) >= 1 && (row.type !== 'hitprcnt' || Number(text) <= 100)
}

/** Il valore da salvare (campi nell'ordine del backend). */
function current(): ITrigger[] {
  return settledTriggers(rows.value.map((r) => ({ type: r.type, argument: r.argument ?? '', block: (BLOCKABLE as readonly string[]).includes(r.type) ? r.block : undefined, chance: r.chance, actions: r.actions })))
}

function changed(): void {
  emit('update:modelValue', current())
}

function add(): void {
  rows.value.push({ key: seq++, type: TRIGGER_TYPES[props.owner][0]!, argument: '', chance: 100, actions: [''] })
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

/** I problemi di trigger (o di condizioni dentro i trigger) della voce, con l'indice del trigger. */
const mine = computed(() =>
  issues.value
    .map((issue, i) => ({ issue, target: targets.value[i] }))
    .filter((x) => x.target?.kind === props.owner && x.target.vnum === props.vnum && triggerIndexOf(x.issue.message) >= 0)
    .map((x) => ({ issue: x.issue, index: triggerIndexOf(x.issue.message) })),
)

/** I problemi del trigger `index` (0-based). */
function issuesOf(index: number): IContentIssue[] {
  return mine.value.filter((x) => x.index === index).map((x) => x.issue)
}
</script>
