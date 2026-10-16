<template>
  <div class="q-pa-md column q-gutter-y-md" style="max-width: 1100px">
    <q-banner v-if="loaded && pairs && pairs.worlds.length < 2" rounded class="bg-orange-2 text-dark" data-testid="convert-need-two">
      {{ t('convert.needTwoWorlds') }}
    </q-banner>

    <template v-else-if="pairs">
      <q-card flat bordered>
        <q-card-section class="text-h6">{{ t('convert.source.title') }}</q-card-section>
        <q-card-section class="column q-gutter-y-md">
          <div class="row q-col-gutter-md">
            <q-select v-model="sourceId" :options="worldOptions" emit-value map-options outlined dense class="col-12 col-md-6" :label="t('convert.source.world')" data-testid="convert-source" @update:model-value="onSource" />
            <q-select v-model="targetId" :options="targetOptions" emit-value map-options outlined dense class="col-12 col-md-6" :label="t('convert.source.target')" data-testid="convert-target" @update:model-value="resetReport" />
          </div>
          <div v-if="pair" class="text-caption text-grey-8" data-testid="convert-converter">{{ t(`convert.converter.${pair.converter}`) }}</div>

          <q-table
            v-model:selected="selected"
            v-model:filter="filter"
            flat
            bordered
            dense
            row-key="id"
            selection="multiple"
            :rows="zones"
            :columns="columns"
            :loading="loadingZones"
            :rows-per-page-options="[10, 25, 0]"
            :title="t('convert.source.zones')"
            data-testid="convert-zones"
            @update:selected="resetReport"
          >
            <template #top-right>
              <q-input v-model="filter" dense outlined clearable :placeholder="t('convert.source.search')" data-testid="convert-zone-search" />
            </template>
          </q-table>
        </q-card-section>
      </q-card>

      <q-card flat bordered>
        <q-card-section class="text-h6">{{ t('convert.options.title') }}</q-card-section>
        <q-card-section class="column q-gutter-y-sm">
          <div class="row q-col-gutter-md">
            <q-select v-model="mode" :options="modeOptions" emit-value map-options outlined dense class="col-12 col-md-4" :label="t('convert.options.vnumPolicy')" data-testid="convert-mode" @update:model-value="resetReport" />
            <q-input v-if="mode === 'offset'" v-model.number="offset" type="number" outlined dense class="col-12 col-md-3" :label="t('convert.options.offset')" data-testid="convert-offset" @update:model-value="resetReport" />
            <q-select v-model="onConflict" :options="conflictOptions" emit-value map-options outlined dense class="col-12 col-md-5" :label="t('convert.options.onConflict')" data-testid="convert-conflict" @update:model-value="resetReport" />
          </div>
          <div class="row">
            <q-checkbox v-model="convertResets" :label="t('convert.options.resets')" @update:model-value="resetReport" />
            <q-checkbox v-model="convertExits" :label="t('convert.options.exits')" @update:model-value="resetReport" />
            <q-checkbox v-model="convertExtras" :label="t('convert.options.extras')" @update:model-value="resetReport" />
          </div>
          <div>
            <q-btn color="primary" outline no-caps :icon="mdiMagnify" :label="t('convert.actions.preview')" :disable="!canPreview" :loading="busy" data-testid="convert-preview" @click="runPreview" />
          </div>
        </q-card-section>
      </q-card>

      <q-card v-if="report" flat bordered>
        <q-card-section>
          <convert-report :report="report" />
        </q-card-section>
        <q-card-section v-if="report.dryRun" class="column q-gutter-y-sm">
          <div class="text-h6">{{ t('convert.run.title') }}</div>
          <q-banner v-if="onConflict === 'replace'" dense rounded class="bg-orange-2 text-dark">{{ t('convert.run.replaceWarn') }}</q-banner>
          <q-checkbox v-model="confirmed" :label="t('convert.run.confirm')" :disable="!anythingToWrite" data-testid="convert-confirm" />
          <div>
            <q-btn color="negative" no-caps :icon="mdiTransfer" :label="t('convert.actions.run')" :disable="!confirmed || !anythingToWrite" :loading="busy" data-testid="convert-run" @click="runConvert" />
          </div>
        </q-card-section>
        <q-card-section v-else class="column q-gutter-y-sm">
          <q-banner v-if="report.applied" rounded class="bg-positive text-white" data-testid="convert-done">
            {{ t('convert.run.done', { zones: writtenZones }) }}
          </q-banner>
          <q-banner v-else rounded class="bg-negative text-white" data-testid="convert-failed">
            {{ report.rolledBack && !report.rollbackErrors.length ? t('convert.run.failed') : t('convert.run.failedNoRollback') }}
          </q-banner>
          <div class="text-caption" data-testid="convert-journal">
            {{ report.journal.enabled ? t('convert.run.journal', { file: report.journal.file ?? '-' }) : t('convert.run.journalOff') }}
          </div>
          <div v-if="report.applied">
            <q-btn color="primary" no-caps :icon="mdiOpenInNew" :label="t('convert.actions.openTarget')" data-testid="convert-open-target" @click="openTarget" />
          </div>
        </q-card-section>
      </q-card>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * Conversione di zone tra mondi: sceglie sorgente, arrivo e zone, mostra l'anteprima (tabelle, tabella dei vnum,
 * perdite raggruppate, conflitti) e solo dopo una conferma esplicita scrive nel mondo di arrivo.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import { mdiMagnify, mdiOpenInNew, mdiTransfer } from '@quasar/extras/mdi-v7'
import ConvertReport from '../components/ConvertReport.vue'
import { describeError } from '../helpers/describe-error'
import { getPairs, listZonesOf, preview, run } from '../services/convert-api'
import { ensureWorlds, selectWorld, useWorld } from '../../shared/helpers/world-state'
import type { IConvertReport, IConvertRequest, IPairs, IZoneRef, VnumMode } from '../types/convert'

const { t } = useI18n()
const $q = useQuasar()
const router = useRouter()
const { loaded } = useWorld()

const pairs = ref<IPairs | null>(null)
const sourceId = ref<string | null>(null)
const targetId = ref<string | null>(null)
const zones = ref<IZoneRef[]>([])
const selected = ref<IZoneRef[]>([])
const filter = ref('')
const loadingZones = ref(false)
const mode = ref<VnumMode>('keep')
const offset = ref(0)
const onConflict = ref<'skip' | 'replace'>('skip')
const convertResets = ref(true)
const convertExits = ref(true)
const convertExtras = ref(true)
const report = ref<IConvertReport | null>(null)
const confirmed = ref(false)
const busy = ref(false)

const columns = [
  { name: 'vnum', label: 'vnum', field: 'vnum', align: 'left' as const, sortable: true },
  { name: 'name', label: 'Nome', field: 'name', align: 'left' as const, sortable: true },
  { name: 'range', label: 'Range', field: (z: IZoneRef) => `${z.bottomVnum}–${z.topVnum}`, align: 'left' as const },
]

const worldOptions = computed(() => (pairs.value?.worlds ?? []).map((w) => ({ value: w.id, label: `${w.name} (${w.kind})` })))
/** Mondi di arrivo: tutti, con il motivo accanto a quelli non ammessi (disabilitati). */
const targetOptions = computed(() =>
  (pairs.value?.worlds ?? []).map((w) => {
    const p = pairs.value?.pairs.find((x) => x.source === sourceId.value && x.target === w.id)
    const reason = p && !p.allowed && p.reason ? ` — ${t(`convert.reasons.${p.reason}`)}` : ''
    return { value: w.id, label: `${w.name} (${w.kind})${reason}`, disable: !!p && !p.allowed }
  }),
)
const pair = computed(() => pairs.value?.pairs.find((x) => x.source === sourceId.value && x.target === targetId.value) ?? null)
const modeOptions = computed(() => (['keep', 'offset', 'shift_to'] as VnumMode[]).map((m) => ({ value: m, label: t(`convert.options.modes.${m}`) })))
const conflictOptions = computed(() => (['skip', 'replace'] as const).map((m) => ({ value: m, label: t(`convert.options.conflicts.${m}`) })))
const canPreview = computed(() => !!pair.value?.allowed && selected.value.length > 0)
const writtenZones = computed(() => report.value?.zones.filter((z) => z.action === 'create' || z.action === 'replace').length ?? 0)
const anythingToWrite = computed(() => !!report.value?.zones.some((z) => z.action === 'create' || z.action === 'replace'))

/** Corpo della richiesta dallo stato della pagina. */
function body(): IConvertRequest {
  return {
    sourceWorld: sourceId.value ?? '',
    targetWorld: targetId.value ?? '',
    zoneIds: selected.value.map((z) => z.id),
    vnumPolicy: { mode: mode.value, offset: mode.value === 'offset' ? offset.value : 0 },
    onConflict: onConflict.value,
    convertResets: convertResets.value,
    convertExits: convertExits.value,
    convertExtraDescriptions: convertExtras.value,
    dryRun: true,
    confirm: false,
  }
}

/** Azzera rapporto e conferma (cambiato qualcosa del piano). */
function resetReport(): void {
  report.value = null
  confirmed.value = false
}

/** Carica le zone del mondo sorgente. */
async function loadZones(): Promise<void> {
  selected.value = []
  zones.value = []
  if (!sourceId.value) return
  loadingZones.value = true
  try {
    zones.value = await listZonesOf(sourceId.value)
  } catch (error) {
    $q.notify({ type: 'negative', message: describeError(error) })
  } finally {
    loadingZones.value = false
  }
}

/** Cambio di mondo sorgente: ricarica le zone e riallinea l'arrivo. */
async function onSource(): Promise<void> {
  resetReport()
  if (pair.value && !pair.value.allowed) targetId.value = pairs.value?.pairs.find((x) => x.source === sourceId.value && x.allowed)?.target ?? null
  await loadZones()
}

/** Anteprima (dry-run). */
async function runPreview(): Promise<void> {
  busy.value = true
  confirmed.value = false
  try {
    report.value = await preview(body())
  } catch (error) {
    report.value = null
    $q.notify({ type: 'negative', message: describeError(error), timeout: 8000 })
  } finally {
    busy.value = false
  }
}

/** Conversione vera (richiede anteprima e conferma). */
async function runConvert(): Promise<void> {
  busy.value = true
  try {
    report.value = await run(body())
  } catch (error) {
    $q.notify({ type: 'negative', message: describeError(error), timeout: 8000 })
  } finally {
    busy.value = false
  }
}

/** Passa al mondo di arrivo e apre l'elenco zone (il selettore di mondo ricarica la pagina). */
async function openTarget(): Promise<void> {
  if (!targetId.value) return
  selectWorld(targetId.value)
  await router.replace('/zones')
  window.location.reload()
}

onMounted(async () => {
  await ensureWorlds()
  try {
    pairs.value = await getPairs()
    sourceId.value = pairs.value.worlds[0]?.id ?? null
    targetId.value = pairs.value.pairs.find((x) => x.source === sourceId.value && x.allowed)?.target ?? null
    await loadZones()
  } catch (error) {
    $q.notify({ type: 'negative', message: describeError(error) })
  }
})
</script>
