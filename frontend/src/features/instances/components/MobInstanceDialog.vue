<template>
  <pachi-dialog
    ref="dialogRef"
    :title="isEdit ? t('instances.mob.editTitle', { id: instance?.id }) : t('instances.mob.createTitle')"
    width="560px"
    max-width="95vw"
    no-backdrop-dismiss
    @hide="onDialogHide()"
  >
      <q-form id="mob-instance-form" @submit.prevent="save">
        <div class="q-gutter-md">
          <q-banner v-if="errorText" class="bg-negative text-white" rounded dense>{{ errorText }}</q-banner>

          <div v-if="instance" class="row q-gutter-sm">
            <q-chip dense clickable :icon="mdiPaw" @click="goTo(prototypeLink)">
              {{ instance.prototypeVnum }} — {{ instance.prototypeName }}
            </q-chip>
            <q-chip dense clickable :icon="mdiDoor" @click="goTo(roomLink)">
              {{ instance.roomVnum }} — {{ instance.roomName }}
            </q-chip>
          </div>
          <prototype-picker
            v-else
            v-model="form.prototypeId"
            kind="mob"
            :disable="!!prototype"
            :rules="[required]"
          />

          <room-picker v-model="form.roomId" :rules="[required]" />

          <div v-if="isEdit" class="row q-col-gutter-md">
            <q-input
              v-model.number="form.hitPointsCurrent"
              class="col"
              type="number"
              :label="t('instances.fields.hitPointsCurrent')"
              :rules="[minOne]"
              outlined
              dense
            />
            <q-input
              v-model.number="form.hitPointsMax"
              class="col"
              type="number"
              :label="t('instances.fields.hitPointsMax')"
              :rules="[minOne]"
              outlined
              dense
            />
          </div>
          <q-input
            v-else
            v-model.number="form.hitPoints"
            type="number"
            :label="t('instances.fields.hitPoints')"
            :hint="t('instances.fields.hitPointsHint')"
            :rules="[optionalMinOne]"
            clearable
            outlined
            dense
          />
          <q-input
            v-model.number="form.gold"
            type="number"
            :label="t('instances.fields.gold')"
            :hint="t('instances.fields.goldHint')"
            :rules="[nonNegative]"
            clearable
            outlined
            dense
          />

          <div v-if="detail && detail.items.length > 0">
            <div class="text-subtitle2">{{ t('instances.mob.items', { count: detail.items.length }) }}</div>
            <q-list dense bordered separator class="rounded-borders">
              <q-item v-for="item in detail.items" :key="item.id">
                <q-item-section>#{{ item.id }} {{ item.prototypeName }}</q-item-section>
                <q-item-section v-if="item.equippedSlot" side>{{ item.equippedSlot }}</q-item-section>
              </q-item>
            </q-list>
          </div>
        </div>
      </q-form>
      <template #actions>
        <q-btn flat :label="t('instances.cancel')" @click="onDialogCancel" />
        <q-btn color="primary" type="submit" form="mob-instance-form" :label="t('instances.save')" :loading="saving" />
      </template>
  </pachi-dialog>
</template>

<script setup lang="ts">
/**
 * Dialog di creazione/modifica di un mob vivo. Lanciato con `$q.dialog({ component: MobInstanceDialog,
 * componentProps: { instance?, prototype? } })`; `onOk` riceve il mob salvato.
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useDialogPluginComponent } from 'quasar'
import { PachiDialog } from '@ilpachi/pachi-kit/dialog'
import { mdiDoor, mdiPaw } from '@quasar/extras/mdi-v7'
import PrototypePicker from './PrototypePicker.vue'
import RoomPicker from './RoomPicker.vue'
import { describeError } from '../helpers/describe-error'
import { toNumberOrNull } from '../helpers/numbers'
import { createMobInstance, getMobInstance, updateMobInstance } from '../services/instances-api'
import type { IMobInstance, IMobInstanceDetail, IPrototypeRef } from '../types/instances'

const props = defineProps<{
  /** Mob da modificare; assente per la creazione. */
  instance?: IMobInstance
  /** Prototipo fisso per la creazione (non modificabile). */
  prototype?: IPrototypeRef
}>()
defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()
const { t } = useI18n()
const router = useRouter()

const isEdit = computed(() => !!props.instance)
const saving = ref(false)
const errorText = ref('')
const detail = ref<IMobInstanceDetail>()

const form = reactive({
  prototypeId: (props.prototype?.id ?? props.instance?.prototypeId ?? null) as number | null,
  roomId: (props.instance?.roomId ?? null) as number | null,
  hitPoints: null as number | null,
  hitPointsCurrent: (props.instance?.hitPointsCurrent ?? 1) as number | null,
  hitPointsMax: (props.instance?.hitPointsMax ?? 1) as number | null,
  gold: (props.instance?.gold ?? null) as number | null,
})

const prototypeLink = computed(() => ({ path: '/mobs', query: { zoneId: props.instance?.prototypeZoneId } }))
const roomLink = computed(() => ({
  path: '/rooms',
  query: { zoneId: props.instance?.zoneId, roomId: props.instance?.roomId },
}))

/** Regola: campo obbligatorio. */
const required = (v: unknown): boolean | string => (v !== null && v !== undefined && v !== '') || t('instances.validation.required')
/** Regola: intero >= 1. */
const minOne = (v: unknown): boolean | string => (Number(v) >= 1) || t('instances.validation.minOne')
/** Regola: vuoto oppure >= 1. */
const optionalMinOne = (v: unknown): boolean | string => v === null || v === '' || v === undefined || Number(v) >= 1 || t('instances.validation.minOne')
/** Regola: vuoto oppure >= 0. */
const nonNegative = (v: unknown): boolean | string => v === null || v === '' || v === undefined || Number(v) >= 0 || t('instances.validation.nonNegative')

/** Chiude il dialog e naviga verso `target`. */
function goTo(target: { path: string; query: Record<string, unknown> }): void {
  onDialogCancel()
  void router.push(target as Parameters<typeof router.push>[0])
}

/** Salva (POST o PUT) e chiude il dialog con il mob risultante; mostra l'errore del backend altrimenti. */
async function save(): Promise<void> {
  errorText.value = ''
  saving.value = true
  try {
    const gold = toNumberOrNull(form.gold)
    const saved = props.instance
      ? await updateMobInstance(props.instance.id, {
          roomId: form.roomId as number,
          hitPointsCurrent: Number(form.hitPointsCurrent),
          hitPointsMax: Number(form.hitPointsMax),
          gold,
        })
      : await createMobInstance({
          prototypeId: form.prototypeId as number,
          roomId: form.roomId as number,
          hitPoints: toNumberOrNull(form.hitPoints),
          gold,
        })
    onDialogOK(saved)
  } catch (error) {
    errorText.value = await describeError(error)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  if (!props.instance) return
  try {
    detail.value = await getMobInstance(props.instance.id)
  } catch {
    // il dettaglio (oggetti trasportati) è facoltativo
  }
})
</script>
