<template>
  <pachi-dialog ref="dialogRef" :title="t('playerFiles.liveInv.edit.title', { name: shownName })" min-width="680px" max-width="95vw" @hide="onDialogHide()">
    <div data-testid="live-item-dialog">
      <q-banner rounded class="bg-warning text-black q-mb-sm" role="note" data-testid="live-item-note">
        <q-badge color="negative" class="q-mr-sm">{{ t('playerFiles.liveInv.live') }}</q-badge>{{ t('playerFiles.liveInv.edit.note', { player: playerName }) }}
      </q-banner>
      <q-banner v-if="error" rounded class="bg-negative text-white q-mb-sm" role="alert" data-testid="live-item-error">{{ error }}</q-banner>
      <q-banner v-if="stale" rounded class="bg-orange-2 text-black q-mb-sm" role="alert" data-testid="live-item-stale">
        {{ t('playerFiles.liveInv.stale') }}
        <template #action>
          <q-btn flat :label="t('playerFiles.liveInv.edit.rebase')" data-testid="live-item-rebase" @click="rebase()" />
        </template>
      </q-banner>

      <template v-if="draft">
        <div class="text-caption q-mb-sm" data-testid="live-item-meta">
          {{ t('playerFiles.liveInv.edit.meta', { vnum: baseItem?.vnum ?? '—', ref: itemRef }) }}
        </div>

        <div class="text-subtitle2 q-mb-xs">{{ t('playerFiles.liveInv.edit.texts') }}</div>
        <q-input
          v-model="draft.name"
          dense
          outlined
          class="q-mb-sm"
          :label="t('playerFiles.liveInv.edit.name')"
          :hint="t('playerFiles.liveInv.edit.nameHint')"
          :error="textErrors.name !== null"
          :error-message="textErrors.name ? t(`playerFiles.liveInv.textError.${textErrors.name}`, { max: TEXT_LIMITS.name }) : ''"
          data-testid="live-item-name"
        />
        <q-input
          v-model="draft.shortDescription"
          dense
          outlined
          class="q-mb-sm"
          :label="t('playerFiles.liveInv.edit.shortDescription')"
          :error="textErrors.shortDescription !== null"
          :error-message="textErrors.shortDescription ? t(`playerFiles.liveInv.textError.${textErrors.shortDescription}`, { max: TEXT_LIMITS.shortDescription }) : ''"
          data-testid="live-item-short"
        />
        <q-input
          v-model="draft.description"
          type="textarea"
          autogrow
          dense
          outlined
          class="q-mb-sm"
          :label="t('playerFiles.liveInv.edit.description')"
          :error="textErrors.description !== null"
          :error-message="textErrors.description ? t(`playerFiles.liveInv.textError.${textErrors.description}`, { max: TEXT_LIMITS.description }) : ''"
          data-testid="live-item-description"
        />

        <div class="text-subtitle2 q-mt-md q-mb-xs">{{ t('playerFiles.liveInv.edit.valuesTitle', { type: typeLabel }) }}</div>
        <div class="row q-col-gutter-sm">
          <div v-for="(_, i) in draft.values" :key="i" class="col-6 col-sm-3">
            <q-input v-model.number="draft.values[i]" type="number" dense outlined :label="valueLabel(i)" :data-testid="`live-item-value-${i}`" />
          </div>
        </div>

        <div class="text-subtitle2 q-mt-md q-mb-xs">{{ t('playerFiles.liveInv.edit.propsTitle') }}</div>
        <div class="row q-col-gutter-sm">
          <div class="col-6 col-sm-3">
            <q-input v-model.number="draft.weight" type="number" dense outlined :label="t('playerFiles.liveInv.edit.weight')" data-testid="live-item-weight" />
          </div>
          <div class="col-6 col-sm-3">
            <q-input
              v-model.number="draft.timer"
              type="number"
              dense
              outlined
              :label="t('playerFiles.liveInv.edit.timer')"
              :hint="t('playerFiles.liveInv.edit.timerHint')"
              data-testid="live-item-timer"
            />
          </div>
          <div class="col-12 col-sm-6">
            <q-select
              v-if="flagOptions.length"
              v-model="flagList"
              :options="flagOptions"
              emit-value
              map-options
              multiple
              use-chips
              dense
              outlined
              :label="t('playerFiles.liveInv.edit.extraFlags')"
              data-testid="live-item-flags"
            />
            <q-input v-else v-model.number="draft.extraFlags" type="number" dense outlined :label="t('playerFiles.liveInv.edit.extraFlags')" data-testid="live-item-flags-number" />
          </div>
        </div>

        <div class="text-subtitle2 q-mt-md q-mb-xs">{{ t('playerFiles.liveInv.edit.affectsTitle') }}</div>
        <div v-for="(affect, i) in draft.affects" :key="i" class="row q-col-gutter-sm q-mb-xs">
          <div class="col-7">
            <q-select
              v-if="applyOptions.length"
              v-model="affect.location"
              :options="applyOptions"
              emit-value
              map-options
              dense
              outlined
              :label="t('playerFiles.liveInv.edit.affectLocation', { n: i + 1 })"
              :data-testid="`live-item-affect-${i}-location`"
            />
            <q-input
              v-else
              v-model.number="affect.location"
              type="number"
              dense
              outlined
              :label="t('playerFiles.liveInv.edit.affectLocation', { n: i + 1 })"
              :data-testid="`live-item-affect-${i}-location`"
            />
          </div>
          <div class="col-5">
            <q-input
              v-model.number="affect.modifier"
              type="number"
              dense
              outlined
              :label="t('playerFiles.liveInv.edit.affectModifier', { n: i + 1 })"
              :data-testid="`live-item-affect-${i}-modifier`"
            />
          </div>
        </div>

        <q-checkbox v-model="save" class="q-mt-md" :label="t('playerFiles.liveInv.edit.save')" data-testid="live-item-save-flag" />
      </template>
      <div v-else-if="loading" class="q-pa-md text-center"><q-spinner size="2em" /></div>
    </div>
    <template #actions>
      <q-btn flat :label="t('playerFiles.cancel')" data-testid="live-item-cancel" @click="onDialogCancel" />
      <q-btn
        color="negative"
        :label="t('playerFiles.liveInv.edit.apply')"
        :disable="!canApply"
        :loading="saving"
        data-testid="live-item-apply"
        @click="apply()"
      />
    </template>
  </pachi-dialog>
</template>

<script setup lang="ts">
/**
 * Modifica di un oggetto istanza di un giocatore connesso (`obj.set`). All'apertura rilegge l'oggetto (`obj.get`) e invia solo i campi
 * cambiati con l'`expect` (vnum + impronta) di quella lettura. Su `stale_ref` il dialogo resta aperto con quanto scritto dall'utente:
 * «ricarica» rilegge l'oggetto allo stesso riferimento e ricalcola le differenze, senza ripetere nulla da solo.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { PachiDialog } from '@ilpachi/pachi-kit/dialog'
import { describeError } from '../../players/helpers/describe-error'
import { errorCode } from '../helpers/error-code'
import { loadLiveEnums } from '../helpers/live-enums'
import {
  type IEnumOpt,
  type IItemDraft,
  TEXT_LIMITS,
  diffDraft,
  draftOf,
  flagsToList,
  listToFlags,
  textProblem,
  valueLabelKey,
} from '../helpers/live-item'
import { getLiveItem, setLiveItem } from '../services/live-api'
import type { ILiveItem } from '../types/live'

const props = defineProps<{
  /** Nome del personaggio connesso. */
  playerName: string
  /** Riferimento dell'oggetto, dall'ultima lettura dell'elenco. */
  itemRef: string
  /** Chiamata quando l'oggetto risulta cambiato (`stale_ref`): l'elenco del chiamante va riletto. */
  onStale?: () => void
}>()

defineEmits([...useDialogPluginComponent.emits])

const { t } = useI18n()
const $q = useQuasar()
const { dialogRef, onDialogHide, onDialogCancel, onDialogOK } = useDialogPluginComponent()

const baseItem = ref<ILiveItem>()
const base = ref<IItemDraft>()
const draft = ref<IItemDraft>()
const enums = ref<Record<string, IEnumOpt[]>>({})
const error = ref('')
const stale = ref(false)
const loading = ref(true)
const saving = ref(false)
const save = ref(true)

const shownName = computed(() => baseItem.value?.shortDescription || props.itemRef)
const flagOptions = computed(() => (enums.value.dikumodExtraFlags ?? []).map((o) => ({ value: o.value, label: o.label })))
const applyOptions = computed(() => (enums.value.dikumodApplyType ?? []).map((o) => ({ value: o.value, label: o.label })))
const typeLabel = computed(() => (enums.value.dikumodItemType ?? []).find((o) => o.value === baseItem.value?.type)?.label ?? String(baseItem.value?.type ?? '—'))

/** Flag come elenco di bit per il selettore multiplo (i bit non descritti restano nella maschera). */
const flagList = computed({
  get: () => flagsToList(draft.value?.extraFlags ?? 0, flagOptions.value),
  set: (list: number[]) => {
    if (draft.value) draft.value.extraFlags = listToFlags(list, base.value?.extraFlags ?? 0, flagOptions.value)
  },
})

/** Problema di ciascun testo (o `null`). */
const textErrors = computed(() => ({
  name: draft.value ? textProblem(draft.value.name, TEXT_LIMITS.name) : null,
  shortDescription: draft.value ? textProblem(draft.value.shortDescription, TEXT_LIMITS.shortDescription) : null,
  description: draft.value ? textProblem(draft.value.description, TEXT_LIMITS.description) : null,
}))

/** Tutti i numeri sono interi nei limiti del protocollo. */
const numbersValid = computed(() => {
  const d = draft.value
  if (!d) return false
  const int = (v: unknown, lo: number, hi: number): boolean => typeof v === 'number' && Number.isInteger(v) && v >= lo && v <= hi
  return (
    d.values.every((v) => int(v, -2147483647, 2147483647)) &&
    int(d.weight, 0, 32767) &&
    int(d.extraFlags, 0, 2147483647) &&
    (d.timer === -7000000 || int(d.timer, 0, 1000000)) &&
    d.affects.every((a) => int(a.location, 0, 64) && int(a.modifier, -32768, 32767))
  )
})

const changes = computed(() => (base.value && draft.value ? diffDraft(base.value, draft.value) : {}))
const canApply = computed(
  () =>
    !saving.value &&
    !stale.value &&
    numbersValid.value &&
    Object.values(textErrors.value).every((p) => p === null) &&
    Object.keys(changes.value).length > 0,
)

/**
 * Etichetta di un valore: il significato per il tipo (`valore N` se generico).
 *
 * @param i - posizione 0..3
 */
function valueLabel(i: number): string {
  const key = valueLabelKey(baseItem.value?.type ?? null, i)
  return key ? t(`playerFiles.liveInv.valueLabel.${key}`, { n: i + 1 }) : t('playerFiles.liveInv.valueN', { n: i + 1 })
}

/** Legge l'oggetto; con `keepInput` le modifiche già fatte dall'utente si conservano e si ricalcolano rispetto alla nuova lettura. */
async function read(keepInput: boolean): Promise<void> {
  const item = await getLiveItem(props.playerName, props.itemRef)
  const fresh = draftOf(item)
  if (keepInput && base.value && draft.value) {
    const mine = diffDraft(base.value, draft.value)
    const merged = draftOf(item)
    if (mine.name !== undefined) merged.name = mine.name
    if (mine.shortDescription !== undefined) merged.shortDescription = mine.shortDescription
    if (mine.description !== undefined) merged.description = mine.description
    if (mine.weight !== undefined) merged.weight = mine.weight
    if (mine.extraFlags !== undefined) merged.extraFlags = mine.extraFlags
    if (mine.timer !== undefined) merged.timer = mine.timer
    mine.values?.forEach((v, i) => v !== null && (merged.values[i] = v))
    mine.affects?.forEach((a, i) => a !== null && (merged.affects[i] = { ...a }))
    draft.value = merged
  } else {
    draft.value = draftOf(item) // copia distinta: `base` non deve cambiare mentre l'utente scrive
  }
  baseItem.value = item
  base.value = fresh
}

/** «Ricarica l'oggetto»: nuova lettura allo stesso riferimento, mantenendo quanto scritto. */
async function rebase(): Promise<void> {
  error.value = ''
  try {
    const previous = baseItem.value?.vnum
    await read(true)
    stale.value = false
    if (previous !== baseItem.value?.vnum) error.value = t('playerFiles.liveInv.edit.otherObject', { vnum: baseItem.value?.vnum ?? '—' })
  } catch (e) {
    error.value = await describeError(e)
  }
}

/** Invia i soli campi cambiati con l'`expect` dell'ultima lettura. */
async function apply(): Promise<void> {
  if (!baseItem.value || !canApply.value) return
  saving.value = true
  error.value = ''
  try {
    const out = await setLiveItem(props.playerName, props.itemRef, {
      expect: { vnum: baseItem.value.vnum, fp: baseItem.value.fp },
      set: changes.value,
      save: save.value,
    })
    if (out.warnings.length) $q.notify({ type: 'warning', message: t('playerFiles.liveInv.warnings', { w: out.warnings.join(', ') }) })
    $q.notify({ type: 'positive', message: out.saved ? t('playerFiles.liveInv.edit.doneSaved') : t('playerFiles.liveInv.edit.doneNotSaved') })
    onDialogOK({ item: out.item })
  } catch (e) {
    if ((await errorCode(e)) === 'worldlive.stale_ref') {
      stale.value = true
      props.onStale?.()
    } else {
      error.value = await describeError(e)
    }
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  enums.value = await loadLiveEnums()
  try {
    await read(false)
  } catch (e) {
    error.value = await describeError(e)
    if ((await errorCode(e)) === 'worldlive.not_found') props.onStale?.()
  } finally {
    loading.value = false
  }
})
</script>
