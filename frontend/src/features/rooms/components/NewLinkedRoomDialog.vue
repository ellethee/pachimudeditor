<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card style="width: 420px; max-width: 95vw" data-testid="new-linked-room-dialog">
      <q-card-section class="text-h6">{{ t('rooms.map.newLinked.title', { from: fromLabel }) }}</q-card-section>
      <q-card-section class="q-gutter-md">
        <q-banner v-if="error" rounded class="bg-negative text-white">{{ error }}</q-banner>
        <q-input v-model="name" outlined dense autofocus :label="t('rooms.fields.name')" data-testid="new-room-name" />
        <q-input v-model.number="vnum" type="number" outlined dense :label="t('rooms.fields.vnum')" />
        <q-select
          v-model="sectorType"
          :options="enums?.sectorType ?? []"
          emit-value
          map-options
          outlined
          dense
          :label="t('rooms.fields.sectorType')"
        />
        <q-select
          v-model="direction"
          :options="freeDirections"
          emit-value
          map-options
          outlined
          dense
          :label="t('rooms.exits.direction')"
        />
        <q-checkbox v-model="withReturn" :label="t('rooms.map.link.withReturn')" />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat no-caps :label="t('rooms.map.cancel')" @click="emit('update:modelValue', false)" />
        <q-btn
          color="primary"
          no-caps
          :label="t('rooms.map.newLinked.create')"
          :loading="saving"
          :disable="!name.trim() || direction === null"
          data-testid="new-room-save"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
/**
 * Piccolo dialogo "nuova stanza collegata": crea una stanza nella zona e l'uscita (con ritorno opzionale) dalla
 * stanza selezionata. Vnum proposto dal backend (`next-vnum`).
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { createExit, createRoom, nextRoomVnum } from '../services/rooms-api'
import { useRoomsStore } from '../stores/use-rooms-store'
import type { IRoomExitInput } from '../types/rooms'
import { OPPOSITE } from '../utils/compass'
import type { DirectionValue } from '../utils/compass'
import { describeError } from '../utils/error-helper'

const props = defineProps<{
  modelValue: boolean
  fromRoomId: number
  fromLabel: string
  zoneId: number
  takenDirections: DirectionValue[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; created: [roomId: number] }>()

const { t, te } = useI18n()
const store = useRoomsStore()
const enums = computed(() => store.enums)
const name = ref('')
const vnum = ref<number | null>(null)
const sectorType = ref(0)
const direction = ref<DirectionValue | null>(null)
const withReturn = ref(true)
const saving = ref(false)
const error = ref('')

const freeDirections = computed(() => (enums.value?.direction ?? []).filter((option) => !props.takenDirections.includes(option.value as DirectionValue)))

/** Payload di un'uscita verso `targetRoomId`. */
function exitPayload(dir: DirectionValue, targetRoomId: number): IRoomExitInput {
  return { direction: dir, description: null, keywords: null, doorFlag: enums.value?.doorFlag[0]?.value ?? 0, isOpen: true, isLocked: false, keyVnum: null, targetRoomId }
}

/** Crea la stanza e i collegamenti. */
async function save(): Promise<void> {
  if (direction.value === null || vnum.value === null) return
  saving.value = true
  error.value = ''
  const silent = { autoError: false }
  try {
    const room = await createRoom(
      { vnum: vnum.value, zoneId: props.zoneId, name: name.value.trim(), description: '', sectorType: sectorType.value, flags: [], healRate: 100, manaRate: 100, clanId: null, owner: null },
      silent,
    )
    await createExit(props.fromRoomId, exitPayload(direction.value, room.id), silent)
    if (withReturn.value) await createExit(room.id, exitPayload(OPPOSITE[direction.value], props.fromRoomId), silent)
    emit('created', room.id)
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
    name.value = ''
    withReturn.value = true
    sectorType.value = enums.value?.sectorType[0]?.value ?? 0
    direction.value = (freeDirections.value[0]?.value as DirectionValue | undefined) ?? null
    vnum.value = await nextRoomVnum(props.zoneId).catch(() => null)
  },
  { immediate: true },
)
</script>
