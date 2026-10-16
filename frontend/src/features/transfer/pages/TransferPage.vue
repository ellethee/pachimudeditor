<template>
  <div class="q-pa-md column q-gutter-y-md" style="max-width: 960px">
    <q-card flat bordered>
      <q-card-section>
        <div class="text-h6">{{ t('transfer.export.title') }}</div>
        <div class="text-body2 text-grey-8">{{ t('transfer.export.description') }}</div>
      </q-card-section>
      <q-card-section class="row items-center q-gutter-md">
        <q-select
          v-model="zoneId"
          :options="zoneOptions"
          emit-value
          map-options
          outlined
          dense
          :label="t('transfer.export.zone')"
          style="min-width: 320px"
          data-testid="export-zone"
        />
        <q-btn
          color="primary"
          no-caps
          :icon="mdiDownload"
          :label="t('transfer.export.download')"
          :disable="zoneId === null"
          :loading="downloading"
          data-testid="export-download"
          @click="download"
        />
      </q-card-section>
    </q-card>

    <q-card flat bordered>
      <q-card-section>
        <div class="text-h6">{{ t('transfer.import.title') }}</div>
        <div class="text-body2 text-grey-8">{{ t('transfer.import.description') }}</div>
      </q-card-section>
      <q-card-section class="column q-gutter-y-md">
        <q-file
          v-model="files"
          multiple
          use-chips
          outlined
          dense
          accept=".zip,.yaml,.yml"
          :label="t('transfer.import.files')"
          :hint="t('transfer.import.filesHint')"
          data-testid="import-files"
          @update:model-value="resetPreview"
        >
          <template #prepend><q-icon :name="mdiPaperclip" /></template>
        </q-file>
        <div>
          <q-btn
            color="primary"
            outline
            no-caps
            :icon="mdiMagnify"
            :label="t('transfer.import.preview')"
            :disable="!files.length"
            :loading="loading"
            data-testid="import-preview"
            @click="runPreview"
          />
        </div>

        <template v-if="preview">
          <q-banner v-if="preview.applied" rounded class="bg-positive text-white" data-testid="import-done">
            {{ t('transfer.import.done', { name: preview.zone.name, vnum: preview.zone.vnum }) }}
          </q-banner>
          <div class="row items-center q-gutter-sm">
            <span class="text-subtitle1">{{ preview.zone.name }} (vnum {{ preview.zone.vnum }})</span>
            <q-badge :color="actionColor[preview.zone.action]" :label="t(`transfer.actions.${preview.zone.action}`)" />
          </div>
          <preview-table :preview="preview" />

          <q-banner v-if="preview.conflicts.length" rounded class="bg-negative text-white" data-testid="import-conflicts">
            <div class="text-weight-medium">{{ t('transfer.conflicts.title') }}</div>
            <ul class="q-my-none">
              <li v-for="c in preview.conflicts" :key="`${c.kind}-${c.vnum}`">
                {{ t('transfer.conflicts.item', { kind: t(`transfer.kind.${c.kind}`), vnum: c.vnum, zone: c.zoneName, zoneVnum: c.zoneVnum }) }}
              </li>
            </ul>
          </q-banner>

          <q-banner v-if="preview.warnings.length" rounded class="bg-orange-2 text-dark" data-testid="import-warnings">
            <div class="text-weight-medium">{{ t('transfer.warnings.title', { count: preview.warnings.length }) }}</div>
            <ul class="q-my-none">
              <li v-for="(w, i) in preview.warnings" :key="i">{{ warningText(w) }}</li>
            </ul>
          </q-banner>

          <div v-if="!preview.applied" class="column q-gutter-y-sm">
            <q-banner dense rounded class="bg-blue-1 text-dark">{{ t('transfer.import.noDeletes') }}</q-banner>
            <q-checkbox v-model="confirmed" :disable="preview.conflicts.length > 0" :label="t('transfer.import.confirm')" data-testid="import-confirm" />
            <div>
              <q-btn
                color="negative"
                no-caps
                :icon="mdiDatabaseImport"
                :label="t('transfer.import.apply')"
                :disable="!confirmed || preview.conflicts.length > 0"
                :loading="loading"
                data-testid="import-apply"
                @click="runApply"
              />
            </div>
          </div>
        </template>
      </q-card-section>
    </q-card>
  </div>
</template>

<script setup lang="ts">
/**
 * Trasferimento zone: esportazione (zip nel formato YAML del game server) e importazione con anteprima
 * (dry-run) seguita da conferma esplicita. L'import fa upsert per vnum e non cancella mai nulla.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { mdiDatabaseImport, mdiDownload, mdiMagnify, mdiPaperclip } from '@quasar/extras/mdi-v7'
import PreviewTable from '../components/PreviewTable.vue'
import { describeError } from '../helpers/describe-error'
import { downloadZoneExport, importZone, listZones } from '../services/transfer-api'
import type { IImportPreview, IImportWarning, IZoneRef, ImportAction } from '../types/transfer'

const { t } = useI18n()
const $q = useQuasar()

const zones = ref<IZoneRef[]>([])
const zoneId = ref<number | null>(null)
const downloading = ref(false)
const files = ref<File[]>([])
const preview = ref<IImportPreview | null>(null)
const confirmed = ref(false)
const loading = ref(false)

/** Colore del badge per ogni azione. */
const actionColor: Record<ImportAction, string> = { create: 'positive', update: 'warning', unchanged: 'grey' }

/** Opzioni della select delle zone: `vnum - nome`. */
const zoneOptions = computed(() => zones.value.map((z) => ({ value: z.id, label: `${z.vnum} - ${z.name}` })))

/** Testo tradotto di un warning. */
function warningText(warning: IImportWarning): string {
  const params: Record<string, string | number> = { ...warning.params }
  if (typeof params.kind === 'string') params.kind = t(`transfer.kind.${params.kind}`)
  return t(`transfer.warnings.codes.${warning.code}`, params)
}

/** Azzera anteprima e conferma (quando cambiano i file). */
function resetPreview(): void {
  preview.value = null
  confirmed.value = false
}

/** Scarica lo zip della zona scelta. */
async function download(): Promise<void> {
  if (zoneId.value === null) return
  downloading.value = true
  try {
    const name = await downloadZoneExport(zoneId.value)
    $q.notify({ type: 'positive', message: t('transfer.export.done', { name }) })
  } catch (error) {
    $q.notify({ type: 'negative', message: describeError(error) })
  } finally {
    downloading.value = false
  }
}

/** Dry-run: mostra cosa farebbe l'import senza scrivere nulla. */
async function runPreview(): Promise<void> {
  loading.value = true
  confirmed.value = false
  try {
    preview.value = await importZone(files.value, false)
  } catch (error) {
    preview.value = null
    $q.notify({ type: 'negative', message: describeError(error), timeout: 8000 })
  } finally {
    loading.value = false
  }
}

/** Import vero (richiede anteprima e conferma). */
async function runApply(): Promise<void> {
  loading.value = true
  try {
    preview.value = await importZone(files.value, true)
    confirmed.value = false
    $q.notify({ type: 'positive', message: t('transfer.import.applied') })
  } catch (error) {
    $q.notify({ type: 'negative', message: describeError(error), timeout: 8000 })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    zones.value = await listZones()
    zoneId.value = zones.value[0]?.id ?? null
  } catch (error) {
    $q.notify({ type: 'negative', message: describeError(error) })
  }
})
</script>
