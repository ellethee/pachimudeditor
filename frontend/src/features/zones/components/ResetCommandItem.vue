<template>
  <q-expansion-item default-opened class="pachi-zone-reset-item">
    <template #header>
      <q-item-section avatar>
        <q-badge color="grey-7">{{ index + 1 }}</q-badge>
      </q-item-section>
      <q-item-section>
        {{ commandTypeLabel(enums, model.commandType) }} — {{ summarize(model) }}
      </q-item-section>
      <q-item-section v-if="issues.length > 0" avatar>
        <q-icon :name="mdiAlertCircle" :color="hasError ? 'negative' : 'warning'" />
      </q-item-section>
      <q-item-section v-if="hasUnknownVnum" avatar>
        <q-icon :name="mdiAlert" color="warning">
          <q-tooltip>{{ t('zones.resets.unknownVnumWarning') }}</q-tooltip>
        </q-icon>
      </q-item-section>
    </template>

    <q-card flat>
      <q-card-section v-if="issues.length > 0" class="q-pb-none">
        <div
          v-for="(issue, i) in issues"
          :key="i"
          :class="issue.level === 'error' ? 'text-negative' : 'text-warning'"
        >
          {{ issue.text }}
        </div>
      </q-card-section>
      <q-card-section class="q-gutter-md">
        <div class="row q-gutter-md items-center">
          <q-select
            :model-value="model.commandType"
            :options="enums?.zoneCommandType ?? []"
            option-value="value"
            option-label="label"
            emit-value
            map-options
            outlined
            dense
            :label="t('zones.resets.type')"
            class="col"
            @update:model-value="changeType"
          />
          <q-input
            v-if="hasIfValue"
            :model-value="model.ifValue ?? (model.ifFlag ? 1 : 0)"
            type="number"
            outlined
            dense
            stack-label
            :label="t('zones.resets.ifValue')"
            :hint="t('zones.resets.ifValueHint')"
            style="width: 220px"
            data-test="reset-if-value"
            @update:model-value="setIfValue"
          />
          <q-checkbox v-else v-model="model.ifFlag" :label="t('zones.resets.ifFlag')" />
          <q-space />
          <q-btn dense flat round :icon="mdiArrowUp" :disable="index === 0" @click="emit('move', -1)" :aria-label="t('zones.resets.moveUp')">
            <q-tooltip>{{ t('zones.resets.moveUp') }}</q-tooltip>
          </q-btn>
          <q-btn dense flat round :icon="mdiArrowDown" :disable="index === count - 1" @click="emit('move', 1)" :aria-label="t('zones.resets.moveDown')">
            <q-tooltip>{{ t('zones.resets.moveDown') }}</q-tooltip>
          </q-btn>
          <q-btn dense flat round color="negative" :icon="mdiDelete" @click="emit('remove')" :aria-label="t('zones.resets.remove')">
            <q-tooltip>{{ t('zones.resets.remove') }}</q-tooltip>
          </q-btn>
        </div>

        <div class="row q-gutter-md">
          <q-input
            v-if="spec.arg1"
            :model-value="model.arg1"
            type="number"
            outlined
            dense
            stack-label
            :label="t(spec.arg1.labelKey)"
            class="col"
            :error="unknownArg1"
            :error-message="errorMessage(spec.arg1, model.arg1)"
            :hint="lookupName(spec.arg1, model.arg1, lookups)"
            @update:model-value="model.arg1 = toNumberOrNull($event)"
          />
          <q-input
            v-if="spec.arg2 === 'number'"
            :model-value="model.arg2"
            type="number"
            outlined
            dense
            stack-label
            :label="t(spec.arg2LabelKey ?? 'zones.resets.maxExisting')"
            class="col"
            @update:model-value="model.arg2 = toNumberOrNull($event)"
          />
          <q-select
            v-if="spec.arg2 === 'direction'"
            v-model="model.arg2"
            :options="enums?.direction ?? []"
            option-value="value"
            option-label="label"
            emit-value
            map-options
            outlined
            dense
            :label="t('zones.resets.direction')"
            class="col"
          />
          <q-input
            v-if="spec.arg3"
            :model-value="model.arg3"
            type="number"
            outlined
            dense
            stack-label
            :label="t(spec.arg3.labelKey)"
            class="col"
            :error="unknownArg3"
            :error-message="errorMessage(spec.arg3, model.arg3)"
            :hint="lookupName(spec.arg3, model.arg3, lookups)"
            @update:model-value="model.arg3 = toNumberOrNull($event)"
          />
          <q-input
            v-if="spec.arg4LabelKey"
            :model-value="model.arg4"
            type="number"
            outlined
            dense
            stack-label
            :label="t(spec.arg4LabelKey)"
            class="col"
            @update:model-value="model.arg4 = toNumberOrNull($event)"
          />
          <q-input
            v-if="spec.argStr === 'text'"
            v-model="model.argStr"
            outlined
            dense
            stack-label
            :label="t('zones.resets.slot')"
            class="col"
          />
          <q-select
            v-if="spec.argStr === 'doorState'"
            v-model="model.argStr"
            :options="[...DOOR_STATES]"
            outlined
            dense
            :label="t('zones.resets.doorState')"
            class="col"
          />
        </div>
        <q-input
          v-if="hasComment"
          v-model="model.comment"
          outlined
          dense
          stack-label
          :label="t('zones.resets.comment')"
          data-test="reset-comment"
        />
      </q-card-section>
    </q-card>
  </q-expansion-item>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWorld } from '../../shared/helpers/world-state'
import { mdiAlert, mdiAlertCircle, mdiArrowDown, mdiArrowUp, mdiDelete } from '@quasar/extras/mdi-v7'
import type { ILookups, IResetCommandInput, IResetIssue, IZoneEnums } from '../types/zones'
import {
  DOOR_STATES,
  commandTypeLabel,
  emptyCommand,
  isUnknownVnum,
  lookupName,
  rowHasUnknownVnum,
  specFor,
  summarize,
  toNumberOrNull,
} from '../utils/reset-commands'
import type { IVnumArgSpec } from '../utils/reset-commands'

/** Editor di un singolo passo dello script di reset (campi variabili in base al tipo di comando). */
const props = withDefaults(defineProps<{
  /** Posizione del passo (0-based). */
  index: number
  /** Numero totale di passi. */
  count: number
  /** Enum del backend (tipi di comando, direzioni). */
  enums: IZoneEnums | null
  /** Vnum noti di stanze, mob e oggetti, per validare gli argomenti. */
  lookups: ILookups
  /** Problemi (errori di salvataggio/validazione) riferiti a questo passo. */
  issues?: IResetIssue[]
}>(), { issues: () => [] })

const emit = defineEmits<{
  /** Sposta il passo di `delta` posizioni. */
  (e: 'move', delta: number): void
  /** Elimina il passo. */
  (e: 'remove'): void
}>()

/** Passo modificato (l'oggetto è mutato in place dal genitore che lo possiede). */
const model = defineModel<IResetCommandInput>({ required: true })

const { t } = useI18n()
const { fieldOf } = useWorld()
/** Il mondo ha `if_flag` intero / il commento di riga (dichiarati e non "unsupported" dal backend). */
const hasIfValue = computed(() => fieldOf('reset_command', 'ifValue')?.unsupported === false)
const hasComment = computed(() => fieldOf('reset_command', 'comment')?.unsupported === false)

const spec = computed(() => specFor(model.value.commandType))
const unknownArg1 = computed(() => isUnknownVnum(spec.value.arg1, model.value.arg1, props.lookups))
const unknownArg3 = computed(() => isUnknownVnum(spec.value.arg3, model.value.arg3, props.lookups))
const hasError = computed(() => props.issues.some((issue) => issue.level === 'error'))
const hasUnknownVnum = computed(() => rowHasUnknownVnum(model.value, props.lookups))

/**
 * Messaggio d'errore per un argomento che referenzia un vnum sconosciuto.
 * @param argSpec specifica dell'argomento
 * @param value vnum inserito
 */
function errorMessage(argSpec: IVnumArgSpec, value: number | null): string {
  if (!isUnknownVnum(argSpec, value, props.lookups)) return ''
  return t('zones.resets.vnumNotFound', { vnum: value ?? '', kind: t(`zones.resets.kinds.${argSpec.kind}`) })
}

/**
 * Imposta la condizione intera e il booleano derivato (`> 0` = condizionato).
 * @param value valore dell'input
 */
function setIfValue(value: string | number | null): void {
  const parsed = toNumberOrNull(value) ?? 0
  model.value.ifValue = parsed
  model.value.ifFlag = parsed > 0
}

/**
 * Cambia il tipo di comando azzerando gli argomenti (hanno significato diverso per ogni tipo).
 * @param commandType nuovo tipo
 */
function changeType(commandType: number): void {
  const { ifFlag, ifValue, comment } = model.value
  Object.assign(model.value, emptyCommand(commandType), { ifFlag, ifValue, comment })
}
</script>
