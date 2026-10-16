<template>
  <q-dialog ref="dialogRef" persistent @hide="onDialogHide">
    <q-card style="width: 600px; max-width: 95vw">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">{{ isEdit ? t('instances.object.editTitle', { id: instance?.id }) : t('instances.object.createTitle') }}</div>
        <q-space />
        <q-btn flat round dense :icon="mdiClose" :aria-label="t('instances.cancel')" @click="onDialogCancel" />
      </q-card-section>

      <q-form @submit.prevent="save">
        <q-card-section class="q-gutter-md">
          <q-banner v-if="errorText" class="bg-negative text-white" rounded dense>{{ errorText }}</q-banner>

          <div v-if="instance" class="row q-gutter-sm">
            <q-chip dense clickable :icon="mdiCubeOutline" @click="goTo(prototypeLink)">
              {{ instance.prototypeVnum }} — {{ instance.prototypeName }}
            </q-chip>
            <q-chip v-if="instance.roomId !== null" dense clickable :icon="mdiDoor" @click="goTo(roomLink)">
              {{ instance.roomVnum }} — {{ instance.roomName }}
            </q-chip>
          </div>
          <prototype-picker
            v-else
            v-model="form.prototypeId"
            kind="object"
            :disable="!!prototype"
            :rules="[required]"
          />

          <div class="text-subtitle2">{{ t('instances.fields.location') }}</div>
          <q-select
            v-model="form.kind"
            :options="kindOptions"
            :label="t('instances.fields.locationKind')"
            emit-value
            map-options
            outlined
            dense
            @update:model-value="onKindChange"
          />
          <room-picker v-if="form.kind === 'room'" v-model="form.targetId" :rules="[required]" />
          <q-input
            v-else
            v-model.number="form.targetId"
            type="number"
            :label="t(`instances.fields.target.${form.kind}`)"
            :hint="t(`instances.fields.targetHint.${form.kind}`)"
            :rules="[required]"
            outlined
            dense
          />
          <q-select
            v-if="form.kind === 'mob' || form.kind === 'character'"
            v-model="form.equippedSlot"
            :options="slotOptions"
            :label="t('instances.fields.equippedSlot')"
            :hint="slotOptions.length === 0 ? t('instances.fields.noSlots') : t('instances.fields.slotHint')"
            :disable="slotOptions.length === 0"
            clearable
            outlined
            dense
          />

          <q-input
            v-if="hasCharges"
            v-model.number="form.charges"
            type="number"
            :label="t('instances.fields.charges')"
            :hint="t('instances.fields.prototypeDefaultHint')"
            :rules="[nonNegative]"
            clearable
            outlined
            dense
          />
          <template v-if="hasLiquid">
            <div class="row q-col-gutter-md">
              <q-input
                v-model.number="form.liquidAmount"
                class="col"
                type="number"
                :label="t('instances.fields.liquidAmount')"
                :hint="t('instances.fields.prototypeDefaultHint')"
                :rules="[nonNegative]"
                clearable
                outlined
                dense
              />
              <q-input
                v-if="isEdit"
                v-model.number="form.liquidType"
                class="col"
                type="number"
                :label="t('instances.fields.liquidType')"
                :hint="t('instances.fields.prototypeDefaultHint')"
                :rules="[nonNegative]"
                clearable
                outlined
                dense
              />
            </div>
            <q-toggle v-if="isEdit" v-model="form.liquidPoisoned" :label="t('instances.fields.liquidPoisoned')" />
          </template>

          <div v-if="detail && detail.contents.length > 0">
            <div class="text-subtitle2">{{ t('instances.object.contents', { count: detail.contents.length }) }}</div>
            <q-list dense bordered separator class="rounded-borders">
              <q-item v-for="item in detail.contents" :key="item.id">
                <q-item-section>#{{ item.id }} {{ item.prototypeName }}</q-item-section>
              </q-item>
            </q-list>
          </div>
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat :label="t('instances.cancel')" @click="onDialogCancel" />
          <q-btn color="primary" type="submit" :label="t('instances.save')" :loading="saving" />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
/**
 * Dialog di creazione/modifica di un oggetto vivo (posizione con room picker, slot, cariche, liquido).
 * Lanciato con `$q.dialog({ component: ObjectInstanceDialog, componentProps: { instance?, prototype? } })`;
 * `onOk` riceve l'oggetto salvato.
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useDialogPluginComponent } from 'quasar'
import { mdiClose, mdiCubeOutline, mdiDoor } from '@quasar/extras/mdi-v7'
import PrototypePicker from './PrototypePicker.vue'
import RoomPicker from './RoomPicker.vue'
import { describeError } from '../helpers/describe-error'
import { toNumberOrNull } from '../helpers/numbers'
import {
  createObjectInstance,
  getObjectInstance,
  getPrototype,
  updateObjectInstance,
} from '../services/instances-api'
import type {
  ILocationInput,
  IObjectInstance,
  IObjectInstanceDetail,
  IPrototypeRef,
  LocationKind,
} from '../types/instances'

/** `ObjectType` delle bacchette/bastoni (hanno cariche). */
const CHARGE_TYPES = [13, 14]
/** `ObjectType` dei contenitori di liquido. */
const LIQUID_TYPE = 4

const props = defineProps<{
  /** Oggetto da modificare; assente per la creazione. */
  instance?: IObjectInstance
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
const detail = ref<IObjectInstanceDetail>()
/** Prototipo corrente (tipo e slot), caricato alla scelta in creazione. */
const proto = ref<IPrototypeRef | undefined>(props.prototype)

const form = reactive({
  prototypeId: (props.prototype?.id ?? props.instance?.prototypeId ?? null) as number | null,
  kind: (props.instance?.locationKind ?? 'room') as LocationKind,
  targetId: (props.instance?.locationId ?? null) as number | null,
  equippedSlot: (props.instance?.equippedSlot ?? null) as string | null,
  charges: (props.instance?.charges ?? null) as number | null,
  liquidAmount: (props.instance?.liquidAmount ?? null) as number | null,
  liquidType: (props.instance?.liquidType ?? null) as number | null,
  liquidPoisoned: (props.instance?.liquidPoisoned ?? null) as boolean | null,
})

const objectType = computed(() => props.instance?.objectType ?? proto.value?.objectType)
const hasCharges = computed(() => objectType.value !== undefined && CHARGE_TYPES.includes(objectType.value))
const hasLiquid = computed(() => objectType.value === LIQUID_TYPE)
const slotOptions = computed(() =>
  (props.instance?.wearSlots ?? proto.value?.wearFlags?.filter((flag) => flag !== 'take') ?? []).slice(),
)
const kindOptions = computed(() =>
  (['room', 'container', 'mob', 'character'] as LocationKind[]).map((value) => ({
    value,
    label: t(`instances.locationKinds.${value}`),
  })),
)
const prototypeLink = computed(() => ({ path: '/objects', query: { zoneId: props.instance?.prototypeZoneId } }))
const roomLink = computed(() => ({
  path: '/rooms',
  query: { zoneId: props.instance?.zoneId, roomId: props.instance?.roomId },
}))

/** Regola: campo obbligatorio. */
const required = (v: unknown): boolean | string => (v !== null && v !== undefined && v !== '') || t('instances.validation.required')
/** Regola: vuoto oppure >= 0. */
const nonNegative = (v: unknown): boolean | string => v === null || v === '' || v === undefined || Number(v) >= 0 || t('instances.validation.nonNegative')

/** Cambiando il tipo di posizione il bersaglio e lo slot non hanno più senso. */
function onKindChange(): void {
  form.targetId = null
  form.equippedSlot = null
}

/** Chiude il dialog e naviga verso `target`. */
function goTo(target: { path: string; query: Record<string, unknown> }): void {
  onDialogCancel()
  void router.push(target as Parameters<typeof router.push>[0])
}

/** Posizione descritta dal form. */
function location(): ILocationInput {
  const slot = form.kind === 'mob' || form.kind === 'character' ? form.equippedSlot : null
  return { kind: form.kind, targetId: Number(form.targetId), equippedSlot: slot }
}

/** Salva (POST o PUT) e chiude il dialog con l'oggetto risultante; mostra l'errore del backend altrimenti. */
async function save(): Promise<void> {
  errorText.value = ''
  saving.value = true
  try {
    const charges = hasCharges.value ? toNumberOrNull(form.charges) : undefined
    const liquidAmount = hasLiquid.value ? toNumberOrNull(form.liquidAmount) : undefined
    const saved = props.instance
      ? await updateObjectInstance(props.instance.id, {
          location: location(),
          ...(charges !== undefined ? { charges } : {}),
          ...(hasLiquid.value
            ? {
                liquidAmount,
                liquidType: toNumberOrNull(form.liquidType),
                liquidPoisoned: form.liquidPoisoned,
              }
            : {}),
        })
      : await createObjectInstance({
          prototypeId: form.prototypeId as number,
          location: location(),
          charges,
          liquidAmount,
        })
    onDialogOK(saved)
  } catch (error) {
    errorText.value = await describeError(error)
  } finally {
    saving.value = false
  }
}

watch(
  () => form.prototypeId,
  async (id) => {
    if (props.instance || props.prototype || id === null) return
    try {
      proto.value = await getPrototype('object', id)
    } catch {
      proto.value = undefined
    }
    form.equippedSlot = null
  },
)

onMounted(async () => {
  if (props.prototype && props.prototype.wearFlags === undefined) {
    try {
      proto.value = await getPrototype('object', props.prototype.id)
    } catch {
      // restano solo i dati passati dal chiamante
    }
  }
  if (!props.instance) return
  try {
    detail.value = await getObjectInstance(props.instance.id)
  } catch {
    // il dettaglio (contenuto) è facoltativo
  }
})
</script>
