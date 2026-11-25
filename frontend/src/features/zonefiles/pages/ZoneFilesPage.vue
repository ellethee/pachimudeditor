<template>
  <div class="q-pa-md column q-gutter-y-md">
    <div class="row q-col-gutter-lg">
      <div class="col-12 col-md-4">
        <div class="row q-col-gutter-sm q-mb-sm">
          <div class="col-6">
            <q-select v-model="zoneFilter" :options="zoneOptions" emit-value map-options dense outlined :label="t('zonefiles.filterZone')" data-testid="zonefiles-filter-zone" />
          </div>
          <div class="col-6">
            <q-select v-model="kindFilter" :options="kindOptions" emit-value map-options dense outlined :label="t('zonefiles.filterKind')" data-testid="zonefiles-filter-kind" />
          </div>
        </div>
        <pachi-table2
          row-key="path"
          :rows="filtered"
          :columns="columns"
          :loading="loading"
          hide-toolbar
          hide-pagination
          single-sort
          :initial-sort="[]"
          dense
          :no-data-label="t('zonefiles.empty')"
          data-testid="zonefiles-list"
        >
          <template #body="{ slotProps: { row } }">
            <q-tr :class="{ 'bg-blue-1': row.path === current?.path }" class="cursor-pointer" :props="{ row }" data-testid="zonefile-row" @click="open(row)">
              <q-td key="zone">{{ row.zone }}</q-td>
              <q-td key="name">{{ row.name }}</q-td>
              <q-td key="kind">{{ t(`zonefiles.kinds.${row.kind}`) }}</q-td>
              <q-td key="size" class="text-right">{{ row.size }}</q-td>
            </q-tr>
          </template>
        </pachi-table2>
      </div>
      <div class="col-12 col-md-8">
        <q-card v-if="current" v-fit-height="{ offset: 24 }" flat bordered class="q-pa-md column no-wrap q-gutter-y-sm" data-testid="zonefile-editor">
          <div class="row items-center q-gutter-sm">
            <div class="text-h6">{{ current.path }}</div>
            <q-badge v-if="dirty" color="warning" text-color="black" :label="t('zonefiles.modified')" data-testid="zonefile-dirty" />
          </div>
          <code-editor ref="editor" v-model="text" language="yaml" :schema="schema" :readonly="readOnly" :error="error" fill data-testid="zonefile-text" />
          <q-banner v-if="changed" dense rounded class="bg-warning text-black" data-testid="zonefile-changed">
            {{ t('zonefiles.changedMessage') }}
            <template #action>
              <q-btn flat no-caps :label="t('zonefiles.reloadDisk')" data-testid="zonefile-reload" @click="reloadFromDisk" />
            </template>
          </q-banner>
          <div v-if="issues.length" class="text-caption scroll" style="max-height: 8em" data-testid="zonefile-issues">
            <div class="text-weight-medium">{{ t('zonefiles.issues', { n: issues.length }) }}</div>
            <ul class="q-my-none">
              <li v-for="(issue, i) in issues" :key="i">
                <span v-if="issue.line">{{ t('zonefiles.issueLine', { line: issue.line }) }} · </span><code>{{ issue.field }}</code>: {{ issue.message }}
              </li>
            </ul>
          </div>
          <div class="row items-center q-gutter-sm">
            <q-btn color="primary" no-caps :icon="mdiContentSave" :label="t('forms.save')" :loading="saving" :disable="!dirty || readOnly" data-testid="zonefile-save" @click="save" />
            <q-btn flat no-caps :label="t('forms.revert')" :disable="!dirty || saving" data-testid="zonefile-revert" @click="revert" />
          </div>
        </q-card>
        <q-banner v-else rounded class="bg-grey-2">{{ t('zonefiles.pick') }}</q-banner>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * File YAML grezzi delle zone pachimud: elenco (filtrabile per zona e tipo; `?zone=<cartella>`) e editor di codice con lo schema JSON
 * del gioco. Il salvataggio mostra gli errori del backend (riga/colonna, violazioni) e, se il file è cambiato sul disco, chiede di
 * ricaricarlo invece di sovrascriverlo.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { mdiContentSave } from '@quasar/extras/mdi-v7'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import { vFitHeight } from '../../shared/directives/fit-height'
import CodeEditor from '../../shared/components/CodeEditor.vue'
import { useWorld } from '../../shared/helpers/world-state'
import { describeError } from '../../content/helpers/describe-error'
import { getSchema } from '../../content/services/content-files-api'
import { getZoneFile, listZoneFiles, parseSaveProblem, putZoneFile } from '../services/zonefiles-api'
import type { IZoneFileContent, IZoneFileEntry, IZoneFileIssue, ZoneFileKind } from '../types/zonefiles'

const { t } = useI18n()
const $q = useQuasar()
const route = useRoute()
const { readOnly } = useWorld()

const rows = ref<IZoneFileEntry[]>([])
const loading = ref(false)
const zoneFilter = ref<string>(typeof route.query.zone === 'string' ? route.query.zone : '')
const kindFilter = ref<ZoneFileKind | ''>('')
const current = ref<IZoneFileContent | null>(null)
const text = ref('')
const original = ref('')
const schema = ref<object | null>(null)
const schemas = new Map<string, object>() // cache per nome
const saving = ref(false)
const error = ref('')
const issues = ref<IZoneFileIssue[]>([])
const changed = ref(false)
const editor = ref<InstanceType<typeof CodeEditor> | null>(null)

const columns: QTableColumn<IZoneFileEntry>[] = [
  { name: 'zone', label: t('zonefiles.columns.zone'), field: 'zone', align: 'left', sortable: true },
  { name: 'name', label: t('zonefiles.columns.file'), field: 'name', align: 'left', sortable: true },
  { name: 'kind', label: t('zonefiles.columns.kind'), field: 'kind', align: 'left', sortable: true },
  { name: 'size', label: t('zonefiles.columns.size'), field: 'size', align: 'right', sortable: true },
]
const zoneOptions = computed(() => [
  { label: t('zonefiles.allZones'), value: '' },
  ...[...new Set(rows.value.map((r) => r.zone))].sort().map((z) => ({ label: z, value: z })),
])
const kindOptions = computed(() => [
  { label: t('zonefiles.allKinds'), value: '' },
  ...(['zone', 'rooms', 'mobs', 'objects', 'resets'] as const).map((k) => ({ label: t(`zonefiles.kinds.${k}`), value: k })),
])
const filtered = computed(() => rows.value.filter((r) => (!zoneFilter.value || r.zone === zoneFilter.value) && (!kindFilter.value || r.kind === kindFilter.value)))
const dirty = computed(() => text.value !== original.value)

watch(() => route.query.zone, (z) => (zoneFilter.value = typeof z === 'string' ? z : ''))

/** Carica l'elenco dei file. */
async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await listZoneFiles()
  } catch (e) {
    $q.notify({ type: 'negative', message: await describeError(e) })
  } finally {
    loading.value = false
  }
}

/** Azzera gli errori di salvataggio. */
function clearProblems(): void {
  error.value = ''
  issues.value = []
  changed.value = false
}

/** Chiede conferma se ci sono modifiche non salvate. */
function confirmDiscard(): Promise<boolean> {
  if (!dirty.value) return Promise.resolve(true)
  return new Promise((resolve) => {
    $q.dialog({ title: t('zonefiles.unsavedTitle'), message: t('zonefiles.unsavedMessage'), cancel: true, persistent: true })
      .onOk(() => resolve(true))
      .onCancel(() => resolve(false))
      .onDismiss(() => resolve(false))
  })
}

/** Schema JSON del file, dalla cache o dal backend (assente = solo sintassi). */
async function schemaFor(name: string): Promise<object | null> {
  if (!schemas.has(name)) {
    try {
      schemas.set(name, await getSchema(name))
    } catch {
      return null
    }
  }
  return schemas.get(name) ?? null
}

/** Mostra un file nell'editor. */
async function show(file: IZoneFileContent): Promise<void> {
  schema.value = await schemaFor(file.schemaName)
  current.value = file
  text.value = original.value = file.text
  clearProblems()
}

/** Apre un file dall'elenco. */
async function open(row: IZoneFileEntry): Promise<void> {
  if (row.path === current.value?.path || !(await confirmDiscard())) return
  try {
    await show(await getZoneFile(row.path))
  } catch (e) {
    $q.notify({ type: 'negative', message: await describeError(e) })
  }
}

/** Rilegge dal disco il file aperto (scarta le modifiche). */
async function reloadFromDisk(): Promise<void> {
  if (!current.value) return
  try {
    await show(await getZoneFile(current.value.path))
    await load()
  } catch (e) {
    $q.notify({ type: 'negative', message: await describeError(e) })
  }
}

/** Salva; gli errori del backend restano sul file (riga/colonna, violazioni, conflitto). */
async function save(): Promise<void> {
  if (!current.value) return
  saving.value = true
  clearProblems()
  try {
    const saved = await putZoneFile(current.value.path, text.value, current.value.etag)
    current.value = saved
    text.value = original.value = saved.text
    $q.notify({ type: 'positive', message: t('zonefiles.saved') })
    await load()
  } catch (e) {
    const problem = await parseSaveProblem(e)
    changed.value = problem.type === 'changed'
    if (!changed.value) error.value = problem.message
    issues.value = problem.issues
    if (problem.line) editor.value?.goToLine(problem.line, problem.column)
  } finally {
    saving.value = false
  }
}

/** Torna al testo salvato. */
function revert(): void {
  text.value = original.value
  clearProblems()
}

/** Avvisa alla chiusura della scheda con modifiche non salvate. */
function beforeUnload(e: BeforeUnloadEvent): void {
  if (dirty.value) e.preventDefault()
}

onBeforeRouteLeave(() => confirmDiscard())
onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload)
  void load()
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>
