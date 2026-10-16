<template>
  <remote-select
    :model-value="modelValue"
    :label="label ?? t('instances.fields.prototype')"
    :fetcher="fetchPrototypes"
    :resolver="resolvePrototype"
    :rules="rules"
    :disable="disable"
    :clearable="clearable"
    @update:model-value="(value: number | null) => emit('update:modelValue', value)"
  />
</template>

<script setup lang="ts">
/**
 * Selettore di prototipo (mob o oggetto) con ricerca per descrizione/keywords/vnum. `v-model` = id.
 */
import { useI18n } from 'vue-i18n'
import RemoteSelect from './RemoteSelect.vue'
import { getPrototype, searchPrototypes } from '../services/instances-api'
import type { InstanceKind, IPrototypeRef, IRemoteOption } from '../types/instances'

const props = defineProps<{
  modelValue: number | null | undefined
  kind: InstanceKind
  label?: string | undefined
  rules?: ((value: unknown) => boolean | string)[] | undefined
  disable?: boolean | undefined
  clearable?: boolean | undefined
}>()
const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()
const { t } = useI18n()

/** Opzione `{ value, label }` di un prototipo. */
function toOption(proto: IPrototypeRef): IRemoteOption {
  return { value: proto.id, label: `${proto.vnum} — ${proto.shortDescription}` }
}

/** Cerca prototipi per testo. */
async function fetchPrototypes(term: string): Promise<IRemoteOption[]> {
  return (await searchPrototypes(props.kind, term)).map(toOption)
}

/** Prototipo di un id. */
async function resolvePrototype(id: number): Promise<IRemoteOption | null> {
  return toOption(await getPrototype(props.kind, id))
}
</script>
