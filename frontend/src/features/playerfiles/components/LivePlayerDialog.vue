<template>
  <pachi-dialog ref="dialogRef" :title="t('playerFiles.live.player.title', { name: playerName })" min-width="640px" max-width="95vw" @hide="onDialogHide()">
    <div data-testid="live-player-dialog">
      <q-banner rounded class="bg-warning text-black q-mb-sm" role="note" data-testid="live-player-note">
        {{ t('playerFiles.live.player.note') }}
      </q-banner>
      <q-banner v-if="error" rounded class="bg-negative text-white q-mb-sm" role="alert" data-testid="live-player-error">{{ error }}</q-banner>

      <div v-if="state" class="row q-col-gutter-sm">
        <div v-for="name in scalarFields" :key="name" class="col-12 col-sm-6">
          <q-input
            v-model.number="draft[name]"
            type="number"
            dense
            outlined
            :label="labelOf(`playerFiles.field.${name}`, name)"
            :data-testid="`live-field-${name}`"
          />
        </div>
      </div>

      <div v-if="levelNames.length" class="q-mt-md">
        <div class="text-subtitle2 q-mb-xs">{{ t('playerFiles.live.player.levels') }}</div>
        <div class="row q-col-gutter-sm">
          <div v-for="name in levelNames" :key="name" class="col-12 col-sm-6">
            <q-input
              v-model.number="draftLevels[name]"
              type="number"
              dense
              outlined
              :label="pretty(name)"
              :data-testid="`live-level-${name}`"
            />
          </div>
        </div>
      </div>

      <div v-if="conditionNames.length" class="q-mt-md">
        <div class="text-subtitle2 q-mb-xs">{{ t('playerFiles.field.conditions') }}</div>
        <div class="row q-col-gutter-sm">
          <div v-for="name in conditionNames" :key="name" class="col-12 col-sm-4">
            <q-input
              v-model.number="draftConditions[name]"
              type="number"
              dense
              outlined
              :label="labelOf(`playerFiles.live.condition.${name}`, name)"
              :data-testid="`live-condition-${name}`"
            />
          </div>
        </div>
      </div>

      <q-checkbox v-model="save" class="q-mt-md" :label="t('playerFiles.live.player.save')" data-testid="live-save-flag" />
      <div v-if="result" class="q-mt-sm text-body2" data-testid="live-player-result">
        {{ result.saved ? t('playerFiles.live.player.appliedSaved', { n: Object.keys(result.applied).length }) : t('playerFiles.live.player.appliedNotSaved', { n: Object.keys(result.applied).length }) }}
      </div>
    </div>
    <template #actions>
      <q-btn flat :label="t('playerFiles.close')" @click="onDialogCancel" />
      <q-btn
        color="primary"
        :label="t('playerFiles.live.player.apply')"
        :disable="!state || saving"
        :loading="saving"
        data-testid="live-apply"
        @click="apply()"
      />
    </template>
  </pachi-dialog>
</template>

<script setup lang="ts">
/**
 * Modifica di un giocatore CONNESSO dal canale live: le modifiche si applicano subito nella memoria del gioco (e, con `save`, anche al
 * file). Un livello da immortale (>= 51) chiede una conferma esplicita e invia `confirmImmortal` solo dopo.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { PachiDialog } from '@ilpachi/pachi-kit/dialog'
import { describeError } from '../../players/helpers/describe-error'
import { errorCode } from '../helpers/error-code'
import { getLivePlayer, setLivePlayer } from '../services/live-api'
import type { ILivePlayerSetResult, ILivePlayerState } from '../types/live'

/** Da questo livello un personaggio è un immortale. */
const IMMORTAL_LEVEL = 51

const props = defineProps<{
  /** Nome del personaggio (come nel gioco). */
  playerName: string
}>()

defineEmits([...useDialogPluginComponent.emits])

const { t, te } = useI18n()
const $q = useQuasar()
const { dialogRef, onDialogHide, onDialogCancel } = useDialogPluginComponent()

const state = ref<ILivePlayerState>()
const error = ref('')
const saving = ref(false)
const save = ref(true)
const result = ref<ILivePlayerSetResult>()
const draft = ref<Record<string, number | null>>({})
const draftLevels = ref<Record<string, number | null>>({})
const draftConditions = ref<Record<string, number | null>>({})

/** Campi numerici semplici modificabili: dichiarati dal MUD (`editableFields`) e presenti in `player.get`. */
const scalarFields = computed(() =>
  (state.value?.editableFields ?? []).filter(
    (name) => name !== 'levels' && name !== 'conditions' && typeof state.value?.fields[name] === 'number',
  ),
)
const editable = computed(() => new Set(state.value?.editableFields ?? []))
const levelNames = computed(() => (editable.value.has('levels') ? Object.keys(asRecord(state.value?.fields.levels)) : []))
const conditionNames = computed(() => (editable.value.has('conditions') ? Object.keys(asRecord(state.value?.fields.conditions)) : []))

/**
 * Un valore come mappa nome -> numero (vuota se non lo è).
 *
 * @param value - valore grezzo di `player.get`
 */
function asRecord(value: unknown): Record<string, number> {
  return value !== null && typeof value === 'object' ? (value as Record<string, number>) : {}
}

/** Etichetta tradotta (ripiega sul nome). */
function labelOf(key: string, fallback: string): string {
  return te(key) ? t(key) : fallback
}

/** `magic_user` -> `Magic user`. */
function pretty(code: string): string {
  const text = code.replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/**
 * Riempie le bozze dai valori correnti.
 *
 * @param next - stato appena letto
 */
function fill(next: ILivePlayerState): void {
  state.value = next
  draft.value = Object.fromEntries(Object.entries(next.fields).filter(([, v]) => typeof v === 'number')) as Record<string, number>
  draftLevels.value = { ...asRecord(next.fields.levels) }
  draftConditions.value = { ...asRecord(next.fields.conditions) }
}

/** I soli campi cambiati rispetto ai valori letti, nella forma del protocollo (`levels`/`conditions` annidati). */
function changes(): { fields: Record<string, unknown>; promotions: [string, number][] } {
  const fields: Record<string, unknown> = {}
  for (const name of scalarFields.value) {
    const value = draft.value[name]
    if (typeof value === 'number' && value !== state.value?.fields[name]) fields[name] = value
  }
  const promotions: [string, number][] = []
  const group = (drafts: Record<string, number | null>, current: Record<string, number>, key: string): void => {
    const changed = Object.fromEntries(Object.entries(drafts).filter(([n, v]) => typeof v === 'number' && v !== current[n]))
    if (Object.keys(changed).length) fields[key] = changed
  }
  group(draftLevels.value, asRecord(state.value?.fields.levels), 'levels')
  group(draftConditions.value, asRecord(state.value?.fields.conditions), 'conditions')
  for (const [name, value] of Object.entries(asRecord(fields.levels))) {
    if (value >= IMMORTAL_LEVEL && value > (asRecord(state.value?.fields.levels)[name] ?? 0)) promotions.push([name, value])
  }
  return { fields, promotions }
}

/**
 * Chiede la conferma esplicita per creare un immortale.
 *
 * @param promotions - classi e nuovo livello
 * @returns `true` se l'utente conferma
 */
function confirmImmortal(promotions: [string, number][]): Promise<boolean> {
  return new Promise((resolve) => {
    $q.dialog({
      title: t('playerFiles.live.immortal.title'),
      message: `${t('playerFiles.live.immortal.warning')} (${promotions.map(([n, v]) => `${pretty(n)} ${v}`).join(', ')})`,
      persistent: true,
      ok: { label: t('playerFiles.live.immortal.confirm'), color: 'negative', 'data-testid': 'immortal-confirm' },
      cancel: { label: t('playerFiles.cancel'), flat: true, 'data-testid': 'immortal-cancel' },
    })
      .onOk(() => resolve(true))
      .onCancel(() => resolve(false))
      .onDismiss(() => resolve(false))
  })
}

/** Applica le modifiche; un livello da immortale solo dopo la conferma. */
async function apply(): Promise<void> {
  const { fields, promotions } = changes()
  if (Object.keys(fields).length === 0) return
  let confirmed = false
  if (promotions.length) {
    confirmed = await confirmImmortal(promotions)
    if (!confirmed) return
  }
  saving.value = true
  error.value = ''
  try {
    let code: string | undefined
    try {
      result.value = await setLivePlayer(props.playerName, { fields, save: save.value, confirmImmortal: confirmed })
    } catch (e) {
      code = await errorCode(e)
      if (code !== 'worldlive.immortal_confirmation_required' || confirmed) throw e
      // il MUD ha riconosciuto una promozione che la bozza non aveva visto: stessa conferma esplicita, poi si riprova
      if (!(await confirmImmortal(promotions.length ? promotions : [['?', IMMORTAL_LEVEL]]))) return
      result.value = await setLivePlayer(props.playerName, { fields, save: save.value, confirmImmortal: true })
    }
    $q.notify({ type: 'positive', message: t('playerFiles.live.player.done') })
    fill(await getLivePlayer(props.playerName))
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    fill(await getLivePlayer(props.playerName))
  } catch (e) {
    error.value = await describeError(e)
  }
})
</script>
