<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card style="width: 420px; max-width: 95vw" data-testid="room-link-dialog">
      <q-card-section class="text-h6">{{ t('rooms.map.link.title') }}</q-card-section>
      <q-card-section class="q-gutter-md">
        <div class="text-body2">{{ fromLabel }} → {{ toLabel }}</div>
        <q-banner v-if="error" rounded class="bg-negative text-white">{{ error }}</q-banner>
        <q-select
          v-model="direction"
          :options="freeDirections"
          emit-value
          map-options
          outlined
          dense
          :label="t('rooms.exits.direction')"
        />
        <q-select
          v-model="doorFlag"
          :options="enums?.doorFlag ?? []"
          emit-value
          map-options
          outlined
          dense
          :label="t('rooms.exits.door')"
        />
        <q-checkbox
          v-model="withReturn"
          :disable="!returnFree"
          :label="returnFree ? t('rooms.map.link.withReturn') : t('rooms.map.link.returnTaken')"
        />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat no-caps :label="t('rooms.map.cancel')" @click="emit('update:modelValue', false)" />
        <q-btn
          color="primary"
          no-caps
          :label="t('rooms.map.link.create')"
          :loading="saving"
          :disable="direction === null"
          data-testid="room-link-save"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
/**
 * Piccolo dialogo di collegamento tra due stanze (trascinando da una maniglia all'altra): direzione, porta e
 * uscita di ritorno opzionale. Crea le uscite una alla volta (`POST /rooms/{id}/exits`).
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { createExit } from '../services/rooms-api'
import { useRoomsStore } from '../stores/use-rooms-store'
import type { IRoomExitInput } from '../types/rooms'
import { OPPOSITE } from '../utils/compass'
import type { DirectionValue } from '../utils/compass'
import { describeError } from '../utils/error-helper'

const props = defineProps<{
  modelValue: boolean
  fromRoomId: number
  toRoomId: number
  fromLabel: string
  toLabel: string
  initialDirection: DirectionValue
  /** Direzioni già usate dalla stanza di partenza e da quella di arrivo. */
  takenFrom: DirectionValue[]
  takenTo: DirectionValue[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; linked: [] }>()

const { t, te } = useI18n()
const store = useRoomsStore()
const enums = computed(() => store.enums)
const direction = ref<DirectionValue | null>(null)
const doorFlag = ref(0)
const withReturn = ref(true)
const saving = ref(false)
const error = ref('')

const freeDirections = computed(() => (enums.value?.direction ?? []).filter((option) => !props.takenFrom.includes(option.value as DirectionValue)))
const returnFree = computed(() => direction.value !== null && !props.takenTo.includes(OPPOSITE[direction.value]))

/** Payload di un'uscita verso `targetRoomId`. */
function exitPayload(dir: DirectionValue, targetRoomId: number): IRoomExitInput {
  return { direction: dir, description: null, keywords: null, doorFlag: doorFlag.value, isOpen: true, isLocked: false, keyVnum: null, targetRoomId }
}

/** Crea l'uscita (e il ritorno, se richiesto e libero). */
async function save(): Promise<void> {
  if (direction.value === null) return
  saving.value = true
  error.value = ''
  try {
    await createExit(props.fromRoomId, exitPayload(direction.value, props.toRoomId), { autoError: false })
    if (withReturn.value && returnFree.value) {
      await createExit(props.toRoomId, exitPayload(OPPOSITE[direction.value], props.fromRoomId), { autoError: false })
    }
    emit('linked')
    emit('update:modelValue', false)
  } catch (e) {
    error.value = await describeError(e, t, te)
  } finally {
    saving.value = false
  }
}

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    await store.ensureEnums()
    error.value = ''
    doorFlag.value = enums.value?.doorFlag[0]?.value ?? 0
    withReturn.value = true
    direction.value = freeDirections.value.some((option) => option.value === props.initialDirection)
      ? props.initialDirection
      : ((freeDirections.value[0]?.value as DirectionValue | undefined) ?? null)
  },
  { immediate: true },
)
</script>
