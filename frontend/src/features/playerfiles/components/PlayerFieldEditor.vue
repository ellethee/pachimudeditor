<template>
  <q-select
    v-if="field.type === 'enum'"
    :model-value="modelValue"
    :options="options"
    emit-value
    map-options
    dense
    outlined
    :aria-label="label"
    :data-testid="`edit-${field.name}`"
    @update:model-value="emit('update:modelValue', $event)"
  />
  <q-select
    v-else-if="field.type === 'flags'"
    :model-value="listValue"
    :options="options"
    option-value="label"
    emit-value
    map-options
    multiple
    use-chips
    dense
    outlined
    :aria-label="label"
    :data-testid="`edit-${field.name}`"
    @update:model-value="emit('update:modelValue', $event)"
  />
  <json-field
    v-else-if="field.type === 'json'"
    :model-value="modelValue"
    :label="label"
    :data-testid="`edit-${field.name}`"
    @update:model-value="emit('update:modelValue', $event)"
  />
  <q-toggle
    v-else-if="field.type === 'boolean'"
    :model-value="modelValue === true"
    :aria-label="label"
    :data-testid="`edit-${field.name}`"
    @update:model-value="emit('update:modelValue', $event)"
  />
  <q-input
    v-else-if="field.type === 'number'"
    :model-value="modelValue === null || modelValue === undefined ? '' : String(modelValue)"
    type="number"
    dense
    outlined
    :aria-label="label"
    :data-testid="`edit-${field.name}`"
    @update:model-value="onNumber"
  />
  <q-input
    v-else
    :model-value="typeof modelValue === 'string' ? modelValue : ''"
    dense
    outlined
    :aria-label="label"
    :data-testid="`edit-${field.name}`"
    @update:model-value="emit('update:modelValue', String($event ?? ''))"
  />
</template>

<script setup lang="ts">
/**
 * Editor di un campo del dettaglio di un giocatore, scelto dal tipo dichiarato dall'adapter
 * (`text|number|boolean|flags|enum|json`).
 */
import { computed } from 'vue'
import JsonField from '../../shared/components/JsonField.vue'
import { localizeOptions } from '../../shared/helpers/enum-labels'
import type { IEnumLabelOption } from '../../shared/helpers/enum-labels'
import type { IExtraFieldDescriptor } from '../../shared/types/worlds'

const props = defineProps<{
  /** Descrittore del campo (`PlayersInfo.detailFields`). */
  field: IExtraFieldDescriptor
  /** Valore corrente della bozza. */
  modelValue: unknown
  /** Enum del mondo (`GET /api/meta/enums`). */
  enums?: Record<string, unknown> | undefined
  /** Etichetta accessibile. */
  label: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

/** Opzioni localizzate dell'enum del campo. */
const options = computed<IEnumLabelOption[]>(() => {
  const list = props.field.enum ? props.enums?.[props.field.enum] : undefined
  return Array.isArray(list) && props.field.enum ? localizeOptions(props.field.enum, list as IEnumLabelOption[]) : []
})

/** Il valore di un campo `flags` come lista di nomi. */
const listValue = computed<string[]>(() => (Array.isArray(props.modelValue) ? props.modelValue.map(String) : []))

/**
 * Valore numerico dal testo dell'input (`null` se vuoto).
 *
 * @param value - testo digitato
 */
function onNumber(value: string | number | null): void {
  emit('update:modelValue', value === null || value === '' ? null : Number(value))
}
</script>
