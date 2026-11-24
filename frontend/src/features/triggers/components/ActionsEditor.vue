<template>
  <div class="column q-gutter-y-xs" data-testid="actions-editor">
    <template v-for="(action, i) in modelValue" :key="i">
      <div v-if="typeof action === 'string'" class="row items-start no-wrap q-gutter-x-xs">
        <q-input
          :model-value="action"
          class="col"
          outlined
          dense
          :readonly="readonly"
          :error="action.trim() === ''"
          :error-message="t('triggers.emptyAction')"
          :hint="actionHint(action)"
          input-style="font-family: monospace"
          data-testid="action-text"
          @update:model-value="setText(i, String($event ?? ''))"
        />
        <q-btn v-if="!readonly" flat round dense color="negative" :icon="mdiDelete" :title="t('triggers.removeAction')" data-testid="action-remove" @click="removeAt(i)" />
      </div>
      <q-card v-else flat bordered class="q-pa-sm bg-blue-grey-1" data-testid="if-block">
        <div class="row items-center q-mb-xs">
          <span class="text-subtitle2">{{ t('triggers.if') }}</span>
          <span class="text-caption text-grey-8 q-ml-sm">{{ t('triggers.ifLevel', { depth }) }}</span>
          <q-space />
          <q-btn v-if="!readonly" flat round dense color="negative" :icon="mdiDelete" :title="t('triggers.removeBlock')" data-testid="if-remove" @click="removeAt(i)" />
        </div>
        <div class="row q-col-gutter-sm">
          <q-input
            :model-value="action.if.chance ?? ''"
            class="col-6 col-sm-2"
            type="number"
            min="1"
            max="100"
            outlined
            dense
            stack-label
            :label="t('triggers.cond.chance')"
            :readonly="readonly"
            :error="action.if.chance !== undefined && !(Number.isInteger(action.if.chance) && action.if.chance >= 1 && action.if.chance <= 100)"
            data-testid="cond-chance"
            @update:model-value="setCond(i, 'chance', $event === '' || $event === null ? undefined : Number($event))"
          />
          <q-input
            v-for="key in ['level', 'hp', 'time', 'vnum'] as const"
            :key="key"
            :model-value="action.if[key] ?? ''"
            class="col-6 col-sm-2"
            outlined
            dense
            stack-label
            :label="t(`triggers.cond.${key}`)"
            :placeholder="key === 'time' ? '>= 20' : '>= 10'"
            :readonly="readonly"
            :error="action.if[key] !== undefined && !(key === 'time' ? validTime(action.if[key]) : validCompare(action.if[key]))"
            :error-message="t(key === 'time' ? 'triggers.cond.badTime' : 'triggers.cond.badCompare')"
            :data-testid="`cond-${key}`"
            @update:model-value="setCond(i, key, compareOf($event))"
          />
          <q-select
            :model-value="action.if.sex ?? null"
            class="col-6 col-sm-2"
            outlined
            dense
            stack-label
            clearable
            emit-value
            map-options
            :options="sexOptions"
            :label="t('triggers.cond.sex')"
            :readonly="readonly"
            data-testid="cond-sex"
            @update:model-value="setCond(i, 'sex', $event ?? undefined)"
          />
          <q-select
            :model-value="action.if.is_player ?? null"
            class="col-6 col-sm-2"
            outlined
            dense
            stack-label
            clearable
            emit-value
            map-options
            :options="playerOptions"
            :label="t('triggers.cond.isPlayer')"
            :readonly="readonly"
            data-testid="cond-is-player"
            @update:model-value="setCond(i, 'is_player', $event ?? undefined)"
          />
          <q-select
            v-if="owner === 'mob'"
            :model-value="action.if.who ?? 'n'"
            class="col-6 col-sm-2"
            outlined
            dense
            stack-label
            emit-value
            map-options
            :options="whoOptions"
            :label="t('triggers.cond.who')"
            :hint="t('triggers.cond.whoHint')"
            :readonly="readonly"
            data-testid="cond-who"
            @update:model-value="setCond(i, 'who', $event === 'n' ? undefined : $event)"
          />
          <q-select
            v-for="key in ['race', 'class'] as const"
            :key="key"
            :model-value="action.if[key] ?? null"
            class="col-12 col-sm-3"
            outlined
            dense
            stack-label
            clearable
            use-input
            hide-selected
            fill-input
            emit-value
            map-options
            input-debounce="0"
            new-value-mode="add"
            :options="optionsOf(key)"
            :label="t(`triggers.cond.${key}`)"
            :readonly="readonly"
            :data-testid="`cond-${key}`"
            @filter="(text: string, update: (fn: () => void) => void) => filterOptions(key, text, update)"
            @new-value="(text: string, done: (v?: string) => void) => done(text.trim())"
            @update:model-value="setCond(i, key, $event || undefined)"
          />
          <q-toggle
            v-for="key in ['is_night', 'is_fighting'] as const"
            :key="key"
            :model-value="action.if[key] ?? null"
            class="col-6 col-sm-2"
            toggle-indeterminate
            dense
            :label="t(`triggers.cond.${key}`)"
            :disable="readonly"
            :data-testid="`cond-${key.replace('_', '-')}`"
            @update:model-value="setCond(i, key, $event ?? undefined)"
          />
          <q-input
            :model-value="action.if.has_effect ?? ''"
            class="col-12 col-sm-3"
            outlined
            dense
            stack-label
            :label="t('triggers.cond.has_effect')"
            :readonly="readonly"
            data-testid="cond-has-effect"
            @update:model-value="setCond(i, 'has_effect', String($event ?? '').trim() || undefined)"
          />
          <q-input
            :model-value="action.if.carries ?? ''"
            class="col-12 col-sm-3"
            outlined
            dense
            stack-label
            :label="t('triggers.cond.carries')"
            :readonly="readonly"
            data-testid="cond-carries"
            @update:model-value="setCond(i, 'carries', String($event ?? '').trim() || undefined)"
          />
        </div>
        <div v-if="unknownKeys(action.if).length" class="q-mt-xs">
          <q-chip v-for="key in unknownKeys(action.if)" :key="key" dense color="negative" text-color="white" :removable="!readonly" data-testid="cond-unknown" @remove="setCond(i, key, undefined)">
            {{ t('triggers.cond.unknown', { key }) }}
          </q-chip>
        </div>
        <div class="text-caption text-grey-8 q-mt-sm">{{ t('triggers.then') }}</div>
        <actions-editor
          class="q-pl-md"
          :model-value="action.then"
          :depth="depth + 1"
          :owner="owner"
          :readonly="readonly"
          :races="races"
          :classes="classes"
          data-testid="if-then"
          @update:model-value="setBranch(i, 'then', $event)"
        />
        <div class="text-caption text-grey-8 q-mt-sm">{{ t('triggers.else') }}</div>
        <actions-editor
          class="q-pl-md"
          :model-value="action.else ?? []"
          :depth="depth + 1"
          :owner="owner"
          :readonly="readonly"
          :races="races"
          :classes="classes"
          :allow-empty="true"
          data-testid="if-else"
          @update:model-value="setBranch(i, 'else', $event)"
        />
      </q-card>
    </template>
    <div v-if="modelValue.length === 0 && !allowEmpty" class="text-negative text-caption">{{ t('triggers.noActions') }}</div>
    <div v-if="!readonly" class="row q-gutter-x-sm">
      <q-btn flat dense no-caps color="primary" :icon="mdiPlus" :label="t('triggers.addAction')" data-testid="action-add" @click="emit('update:modelValue', [...modelValue, ''])" />
      <q-btn
        flat
        dense
        no-caps
        color="primary"
        :icon="mdiSourceBranch"
        :label="t('triggers.addIf')"
        :disable="depth > MAX_IF_DEPTH"
        :title="depth > MAX_IF_DEPTH ? t('triggers.maxDepth', { max: MAX_IF_DEPTH }) : undefined"
        data-testid="if-add"
        @click="emit('update:modelValue', [...modelValue, { if: {}, then: [''] }])"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Elenco di azioni di un trigger: righe di comando (una per azione) e blocchi `if`/`then`/`else` annidati fino a 3 livelli, con le
 * condizioni come campi tipizzati (razza e classe con suggerimento dai cataloghi dell'editor). Ricorsivo: ogni ramo è un altro
 * `ActionsEditor`. Non modifica mai il suo `modelValue`: emette sempre una copia nuova.
 */
import { computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiDelete, mdiPlus, mdiSourceBranch } from '@quasar/extras/mdi-v7'
import { isRoomVerb, MAX_IF_DEPTH, mpUsage, validCompare, validTime } from '../helpers/triggers'
import type { ICondition, IIfBlock, TAction, TriggerOwner } from '../types/triggers'

const props = withDefaults(
  defineProps<{
    modelValue: TAction[]
    depth?: number
    owner?: TriggerOwner
    readonly?: boolean
    races?: { id: string; name: string }[]
    classes?: { id: string; name: string }[]
    /** Un ramo `else` può essere vuoto. */
    allowEmpty?: boolean
  }>(),
  { depth: 1, owner: 'mob', readonly: false, races: () => [], classes: () => [], allowEmpty: false },
)
const emit = defineEmits<{ 'update:modelValue': [value: TAction[]] }>()
const { t } = useI18n()

const KNOWN = ['chance', 'level', 'hp', 'sex', 'race', 'class', 'carries', 'is_player', 'who', 'time', 'is_night', 'is_fighting', 'has_effect', 'vnum']

/** Suggerimento sotto una riga di azione: la sintassi di un comando MP (mob) o l'avviso che oggetti e stanze non lo ammettono. */
function actionHint(action: string): string | undefined {
  if (action.trim() === '') return undefined
  if (props.owner !== 'mob') return isRoomVerb(action) ? undefined : t('triggers.verbHint')
  const usage = mpUsage(action)
  return usage ? t('triggers.mpUsage', { usage }) : undefined
}
const sexOptions = computed(() => ['male', 'female', 'other'].map((value) => ({ value, label: t(`triggers.cond.sexes.${value}`) })))
const playerOptions = computed(() => [
  { value: true, label: t('triggers.cond.player') },
  { value: false, label: t('triggers.cond.npc') },
])
const whoOptions = computed(() => [
  { value: 'n', label: t('triggers.cond.whoN') },
  { value: 'i', label: t('triggers.cond.whoI') },
])

/** Il testo digitato nei campi razza e classe (filtra i suggerimenti). */
const typed = reactive({ race: '', class: '' })
function optionsOf(key: 'race' | 'class'): { value: string; label: string }[] {
  const needle = typed[key].trim().toLowerCase()
  const all = (key === 'race' ? props.races : props.classes).map((x) => ({ value: x.id, label: `${x.name} (${x.id})` }))
  return needle ? all.filter((o) => o.label.toLowerCase().includes(needle)) : all
}
function filterOptions(key: 'race' | 'class', text: string, update: (fn: () => void) => void): void {
  update(() => {
    typed[key] = text
  })
}

/** Le chiavi di una condizione che l'editor non conosce (si conservano e si possono togliere). */
function unknownKeys(cond: ICondition): string[] {
  return Object.keys(cond).filter((k) => !KNOWN.includes(k))
}

/** `level`/`hp`: un numero intero resta numero, un confronto resta testo, vuoto = assente. */
function compareOf(value: unknown): number | string | undefined {
  const text = String(value ?? '').trim()
  return text === '' ? undefined : /^-?\d+$/.test(text) ? Number(text) : text
}

function replaceAt(index: number, action: TAction): void {
  emit('update:modelValue', props.modelValue.map((x, i) => (i === index ? action : x)))
}
function removeAt(index: number): void {
  emit('update:modelValue', props.modelValue.filter((_, i) => i !== index))
}
function setText(index: number, text: string): void {
  replaceAt(index, text)
}
function setCond(index: number, key: string, value: unknown): void {
  const block = props.modelValue[index] as IIfBlock
  const cond: ICondition = { ...block.if }
  if (value === undefined) delete cond[key]
  else cond[key] = value
  replaceAt(index, { ...block, if: cond })
}
function setBranch(index: number, branch: 'then' | 'else', value: TAction[]): void {
  const block = { ...(props.modelValue[index] as IIfBlock), [branch]: value }
  if (branch === 'else' && value.length === 0) delete block.else
  replaceAt(index, block)
}
</script>
