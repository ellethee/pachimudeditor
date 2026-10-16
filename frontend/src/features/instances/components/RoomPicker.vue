<template>
  <remote-select
    :model-value="modelValue"
    :label="label ?? t('instances.fields.room')"
    :fetcher="fetchRooms"
    :resolver="resolveRoom"
    :rules="rules"
    :hint="hint"
    :disable="disable"
    :clearable="clearable"
    @update:model-value="(value: number | null) => emit('update:modelValue', value)"
  />
</template>

<script setup lang="ts">
/**
 * Selettore di stanza con ricerca per nome/vnum su `/api/rooms`. Il `v-model` è l'id della stanza.
 */
import { useI18n } from 'vue-i18n'
import RemoteSelect from './RemoteSelect.vue'
import { getRoom, searchRooms } from '../services/instances-api'
import type { IRemoteOption, IRoomRef } from '../types/instances'

defineProps<{
  modelValue: number | null | undefined
  label?: string | undefined
  hint?: string | undefined
  rules?: ((value: unknown) => boolean | string)[] | undefined
  disable?: boolean | undefined
  clearable?: boolean | undefined
}>()
const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()
const { t } = useI18n()

/** Opzione `{ value, label }` di una stanza. */
function toOption(room: IRoomRef): IRemoteOption {
  return { value: room.id, label: `${room.vnum} — ${room.name}` }
}

/** Cerca stanze per testo. */
async function fetchRooms(term: string): Promise<IRemoteOption[]> {
  return (await searchRooms(term)).map(toOption)
}

/** Stanza di un id (o `null`). */
async function resolveRoom(id: number): Promise<IRemoteOption | null> {
  return toOption(await getRoom(id))
}
</script>
