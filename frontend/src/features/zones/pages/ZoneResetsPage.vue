<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <q-btn flat round :icon="mdiArrowLeft" to="/zones" :aria-label="t('zones.resets.back')">
        <q-tooltip>{{ t('zones.resets.back') }}</q-tooltip>
      </q-btn>
      <h1 class="text-h5 q-my-none">{{ t('zones.resets.title') }}</h1>
      <q-select
        :model-value="zoneId"
        :options="zones"
        option-value="id"
        :option-label="zoneLabel"
        emit-value
        map-options
        outlined
        dense
        :label="t('zones.resets.zone')"
        style="min-width: 280px"
        @update:model-value="selectZone"
      />
      <q-space />
      <q-btn
        flat
        :icon="mdiCheckDecagram"
        :label="t('zones.resets.validate')"
        no-caps
        :loading="validating"
        :disable="!zoneKnown || rows.length === 0"
        @click="validate"
      />
      <q-btn
        flat
        :icon="mdiPlus"
        :label="t('zones.resets.addStep')"
        no-caps
        :disable="!zoneKnown || readOnly"
        @click="addRow"
      />
      <q-btn
        color="primary"
        :icon="mdiContentSave"
        :label="t('zones.resets.save')"
        no-caps
        :loading="saving"
        :disable="!zoneKnown || !dirty || readOnly"
        @click="save"
      />
    </div>

    <pachi-loading-state v-if="loading" />
    <div v-else-if="!zoneKnown" class="text-grey">{{ t('zones.resets.zoneNotFound') }}</div>
    <div v-else-if="rows.length === 0" class="text-grey">{{ t('zones.resets.empty') }}</div>

    <q-banner
      v-if="validatedOk && issues.length === 0"
      rounded
      class="bg-positive text-white q-mb-md"
      data-test="reset-validation-ok"
    >
      {{ t('zones.resets.validationOk') }}
    </q-banner>
    <q-banner v-else-if="globalIssues.length > 0" rounded class="bg-negative text-white q-mb-md">
      <div v-for="(issue, i) in globalIssues" :key="i">{{ issue.text }}</div>
    </q-banner>

    <q-list v-if="!loading && zoneKnown && rows.length > 0" bordered separator>
      <reset-command-item
        v-for="(row, index) in rows"
        :key="row.uid"
        v-model="row.cmd"
        :index="index"
        :count="rows.length"
        :enums="enums"
        :lookups="lookups"
        :issues="issuesFor(index)"
        @move="move(index, $event)"
        @remove="rows.splice(index, 1)"
      />
    </q-list>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { mdiArrowLeft, mdiCheckDecagram, mdiContentSave, mdiPlus } from '@quasar/extras/mdi-v7'
import { PachiLoadingState } from '@ilpachi/pachifastquasar'
import ResetCommandItem from '../components/ResetCommandItem.vue'
import { loadLookups } from '../services/lookups-api'
import { getResetCommands, listAllZones, replaceResetCommands, validateResetCommands } from '../services/zones-api'
import { useZonesStore } from '../stores/use-zones-store'
import { useWorld } from '../../shared/helpers/world-state'
import type { ILookups, IResetCommandInput, IResetIssue, IZone } from '../types/zones'
import { emptyCommand, isIncomplete } from '../utils/reset-commands'
import { issuesFromError } from '../utils/reset-issues'

/** Passo in modifica con un identificatore locale stabile (chiave di rendering, non inviato al backend). */
interface IEditableRow {
  uid: number
  cmd: IResetCommandInput
}

const { t } = useI18n()
const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const store = useZonesStore()
const { readOnly, fieldOf } = useWorld()
const hasIfValue = computed(() => fieldOf('reset_command', 'ifValue')?.unsupported === false)
const hasComment = computed(() => fieldOf('reset_command', 'comment')?.unsupported === false)

const zones = ref<IZone[]>([])
const rows = ref<IEditableRow[]>([])
const loading = ref(true)
const saving = ref(false)
const validating = ref(false)
/** Problemi dell'ultimo salvataggio fallito o dell'ultima validazione. */
const issues = ref<IResetIssue[]>([])
/** `true` dopo una validazione conclusa (distingue "nessun problema" da "mai validato"). */
const validatedOk = ref(false)
const lookups = reactive<ILookups>({ room: new Map(), mob: new Map(), object: new Map() })
/** Istantanea JSON dello script come salvato, per sapere se ci sono modifiche. */
const baseline = ref('[]')
let nextUid = 1

const enums = computed(() => store.enums)
const zoneId = computed(() => Number(route.params.id))
const zoneKnown = computed(() => zones.value.some((zone) => zone.id === zoneId.value))
const dirty = computed(() => serialize() !== baseline.value)

/** Problemi che non si riferiscono a un passo preciso (o a un passo inesistente). */
const globalIssues = computed(() =>
  issues.value.filter((issue) => issue.index === null || issue.index < 0 || issue.index >= rows.value.length),
)

/**
 * Problemi riferiti a un passo.
 * @param index posizione (0-based) del passo
 */
function issuesFor(index: number): IResetIssue[] {
  return issues.value.filter((issue) => issue.index === index)
}

/** Serializza i passi correnti (senza `uid`) per il confronto con l'istantanea. */
function serialize(): string {
  return JSON.stringify(rows.value.map((row) => row.cmd))
}

/**
 * Etichetta di una zona nel selettore.
 * @param zone zona
 */
function zoneLabel(zone: IZone): string {
  return `${zone.vnum} - ${zone.name}`
}

/** Aggiunge un passo vuoto in fondo (tipo iniziale: il primo degli enum). */
function addRow(): void {
  rows.value.push({ uid: nextUid++, cmd: emptyCommand(enums.value?.zoneCommandType[0]?.value ?? 0) })
}

/**
 * Sposta un passo.
 * @param index posizione attuale
 * @param delta spostamento (-1 su, +1 giù)
 */
function move(index: number, delta: number): void {
  const target = index + delta
  if (target < 0 || target >= rows.value.length) return
  const [row] = rows.value.splice(index, 1)
  if (row) rows.value.splice(target, 0, row)
}

/** Carica lo script della zona corrente e ne fissa l'istantanea. */
async function loadRows(): Promise<void> {
  if (!zoneKnown.value) {
    rows.value = []
    baseline.value = '[]'
    return
  }
  loading.value = true
  try {
    const commands = await getResetCommands(zoneId.value)
    rows.value = [...commands]
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .map((c) => ({
        uid: nextUid++,
        cmd: {
          commandType: c.commandType,
          ifFlag: c.ifFlag,
          arg1: c.arg1,
          arg2: c.arg2,
          arg3: c.arg3,
          arg4: c.arg4,
          argStr: c.argStr,
          // solo nei mondi che li dichiarano (Diku Modificato): senza, un salvataggio perderebbe condizione e commento
          ...(hasIfValue.value ? { ifValue: c.ifValue ?? (c.ifFlag ? 1 : 0) } : {}),
          ...(hasComment.value ? { comment: c.comment ?? null } : {}),
        },
      }))
    baseline.value = serialize()
  } finally {
    loading.value = false
  }
}

/** Salva l'intero script (sostituisce quello esistente). */
async function save(): Promise<void> {
  const incomplete = rows.value.findIndex((row) => isIncomplete(row.cmd))
  if (incomplete >= 0) {
    $q.notify({ type: 'warning', message: t('zones.resets.incomplete', { step: incomplete + 1 }) })
    return
  }
  saving.value = true
  issues.value = []
  validatedOk.value = false
  try {
    await replaceResetCommands(
      zoneId.value,
      rows.value.map((row) => row.cmd),
    )
    baseline.value = serialize()
    $q.notify({ type: 'positive', message: t('zones.resets.saved') })
  } catch (error) {
    issues.value = await issuesFromError(error)
    $q.notify({ type: 'negative', message: t('zones.resets.saveFailed', { count: issues.value.length }) })
  } finally {
    saving.value = false
  }
}

/** Valida lo script corrente (anche non salvato) e mostra i problemi per passo. */
async function validate(): Promise<void> {
  validating.value = true
  validatedOk.value = false
  try {
    issues.value = await validateResetCommands(
      zoneId.value,
      rows.value.map((row) => row.cmd),
    )
    validatedOk.value = true
  } catch (error) {
    issues.value = await issuesFromError(error)
  } finally {
    validating.value = false
  }
}

/**
 * Cambia zona navigando verso la sua route (la guardia chiede conferma se ci sono modifiche).
 * @param id id della zona scelta
 */
function selectZone(id: number): void {
  void router.push(`/zones/${id}/resets`)
}

/**
 * Chiede conferma se ci sono modifiche non salvate.
 * @returns `true` se si può proseguire
 */
function confirmLeave(): Promise<boolean> {
  if (!dirty.value) return Promise.resolve(true)
  return new Promise((resolve) => {
    $q.dialog({
      title: t('zones.resets.unsavedTitle'),
      message: t('zones.resets.unsavedMessage'),
      cancel: true,
      persistent: true,
      ok: { label: t('zones.resets.discard'), flat: true, color: 'negative' },
    })
      .onOk(() => resolve(true))
      .onCancel(() => resolve(false))
      .onDismiss(() => resolve(false))
  })
}

onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate(confirmLeave)

watch(zoneId, () => {
  issues.value = []
  validatedOk.value = false
  void loadRows()
})

onMounted(async () => {
  try {
    const [, list, known] = await Promise.all([store.ensureEnums(), listAllZones(), loadLookups()])
    zones.value = list
    Object.assign(lookups, known)
    await loadRows()
  } finally {
    loading.value = false
  }
})
</script>
