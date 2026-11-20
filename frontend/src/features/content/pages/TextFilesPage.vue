<template>
  <div class="q-pa-md column q-gutter-y-md">
    <content-live-bar ref="bar" :kind="kind" />
    <div class="row q-col-gutter-lg">
      <div class="col-12 col-md-4">
        <q-table
          flat
          bordered
          dense
          row-key="key"
          :rows="rows"
          :columns="columns"
          :loading="loading"
          :filter="filter"
          :pagination="{ rowsPerPage: 15 }"
          :rows-per-page-options="[15, 30, 0]"
          :no-data-label="t('content.empty')"
          data-testid="files-list"
        >
          <template #top>
            <q-btn color="primary" no-caps :icon="mdiPlus" :label="t('content.files.create')" :disable="readOnly" data-testid="file-create" @click="startCreate" />
            <q-space />
            <q-input v-model="filter" dense outlined clearable :placeholder="t('content.search')" style="min-width: 160px">
              <template #prepend><q-icon :name="mdiMagnify" /></template>
            </q-input>
          </template>
          <template #body="{ row }">
            <q-tr :class="{ 'bg-blue-1': row.key === currentKey }" class="cursor-pointer" :props="{ row }" data-testid="file-row" @click="open(row)">
              <q-td key="path">{{ row.path }}</q-td>
              <q-td key="layer" class="text-right" auto-width>
                <q-badge v-if="row.layer === 'user'" color="primary" outline :label="t('content.layer.user')" />
                <q-badge v-else color="grey" outline :label="t('content.layer.base')" />
              </q-td>
            </q-tr>
          </template>
        </q-table>
      </div>
      <div class="col-12 col-md-8">
        <q-card v-if="current" flat bordered class="q-pa-md column q-gutter-y-sm" data-testid="file-editor">
          <div class="row items-center">
            <div class="text-h6">{{ current.path }}</div>
            <q-badge v-if="current.layer === 'base'" class="q-ml-md" color="grey" outline :label="t('content.layer.baseHint')" />
            <q-space />
            <q-btn
              v-if="current.layer === 'user' && !isNew"
              flat
              no-caps
              color="negative"
              :icon="mdiDelete"
              :label="t('content.actions.delete')"
              :disable="readOnly"
              data-testid="file-delete"
              @click="remove"
            />
          </div>
          <q-input
            v-if="isNew"
            v-model="newPath"
            outlined
            dense
            :label="t('content.files.path')"
            :hint="t('content.files.pathHint', { ext: area === 'texts' ? '.txt' : '.yaml' })"
            data-testid="file-path"
          />
          <q-input
            v-model="text"
            type="textarea"
            outlined
            autogrow
            :readonly="readOnly"
            input-style="font-family: monospace; min-height: 16em"
            data-testid="file-text"
          />
          <q-banner v-if="error" dense rounded class="bg-negative text-white" data-testid="file-error">{{ error }}</q-banner>
          <div class="row items-center q-gutter-sm">
            <q-btn color="primary" no-caps :icon="mdiContentSave" :label="t('forms.save')" :loading="saving" :disable="!dirty || readOnly" data-testid="file-save" @click="save" />
            <q-btn flat no-caps :label="t('forms.revert')" :disable="!dirty || saving" data-testid="file-revert" @click="revert" />
          </div>
        </q-card>
        <q-banner v-else rounded class="bg-grey-2">{{ t('content.files.pick') }}</q-banner>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Editor di file di testo a strati (tabelle, cataloghi dei messaggi, testi lunghi): elenco e testo YAML/TXT inline. Si scrive sempre
 * nello strato dell'utente (un file di serie viene copiato); il backend rifiuta un YAML che non si legge, con riga e colonna. Dopo il
 * salvataggio il gioco, se il canale live c'è, controlla i file e i problemi compaiono nel pannello.
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiContentSave, mdiDelete, mdiMagnify, mdiPlus } from '@quasar/extras/mdi-v7'
import ContentLiveBar from '../components/ContentLiveBar.vue'
import { useWorld } from '../../shared/helpers/world-state'
import { describeError } from '../helpers/describe-error'
import { deleteFile, getFile, listFiles, putFile } from '../services/content-files-api'
import type { FileArea, IFileContent, IFileEntry, ReloadKind } from '../types/content-files'

const props = defineProps<{
  /** Aree mostrate (la prima è quella dei file nuovi). */
  areas: FileArea[]
  /** Cosa rilegge «Ricarica nel gioco». */
  kind: ReloadKind
}>()

interface IRow extends IFileEntry {
  area: FileArea
  key: string
}

const { t } = useI18n()
const $q = useQuasar()
const { readOnly } = useWorld()

const rows = ref<IRow[]>([])
const loading = ref(false)
const filter = ref('')
const current = ref<IFileContent | null>(null)
const area = ref<FileArea>(props.areas[0] ?? 'tables')
const isNew = ref(false)
const newPath = ref('')
const text = ref('')
const original = ref('')
const saving = ref(false)
const error = ref('')
const bar = ref<InstanceType<typeof ContentLiveBar> | null>(null)

const columns: QTableColumn<IRow>[] = [
  { name: 'path', label: t('content.files.file'), field: 'path', align: 'left', sortable: true },
  { name: 'layer', label: '', field: 'layer', align: 'right' },
]
const currentKey = computed(() => (current.value && !isNew.value ? `${area.value}/${current.value.path}` : null))
const dirty = computed(() => text.value !== original.value || (isNew.value && newPath.value.trim() !== ''))

/** Carica gli elenchi di tutte le aree. */
async function load(): Promise<void> {
  loading.value = true
  try {
    const all = await Promise.all(props.areas.map(async (a) => (await listFiles(a)).map((f) => ({ ...f, area: a, key: `${a}/${f.path}` }))))
    rows.value = all.flat()
  } catch (e) {
    $q.notify({ type: 'negative', message: await describeError(e) })
  } finally {
    loading.value = false
  }
}

/** Chiede conferma se ci sono modifiche non salvate. */
function confirmDiscard(): Promise<boolean> {
  if (!dirty.value) return Promise.resolve(true)
  return new Promise((resolve) => {
    $q.dialog({ title: t('content.unsavedTitle'), message: t('content.unsavedMessage'), cancel: true, persistent: true })
      .onOk(() => resolve(true))
      .onCancel(() => resolve(false))
      .onDismiss(() => resolve(false))
  })
}

/** Apre un file nell'editor. */
async function open(row: IRow): Promise<void> {
  if (row.key === currentKey.value || !(await confirmDiscard())) return
  try {
    const file = await getFile(row.area, row.path)
    area.value = row.area
    isNew.value = false
    current.value = file
    text.value = original.value = file.text
    error.value = ''
  } catch (e) {
    $q.notify({ type: 'negative', message: await describeError(e) })
  }
}

/** Apre l'editor per un file nuovo (area di default: la prima). */
async function startCreate(): Promise<void> {
  if (!(await confirmDiscard())) return
  area.value = props.areas[0] ?? 'tables'
  isNew.value = true
  newPath.value = ''
  current.value = { path: t('content.files.newFile'), layer: 'user', text: '' }
  text.value = original.value = ''
  error.value = ''
}

/** Salva nello strato dell'utente e fa controllare i file al gioco. */
async function save(): Promise<void> {
  const path = isNew.value ? newPath.value.trim() : (current.value as IFileContent).path
  saving.value = true
  error.value = ''
  try {
    const saved = await putFile(area.value, path, text.value)
    isNew.value = false
    current.value = saved
    text.value = original.value = saved.text
    $q.notify({ type: 'positive', message: t('content.savedLayered') })
    await load()
    await nextTick()
    await bar.value?.validate()
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    saving.value = false
  }
}

/** Torna al testo salvato. */
function revert(): void {
  text.value = original.value
  if (isNew.value) newPath.value = ''
  error.value = ''
}

/** Elimina il file dello strato dell'utente dopo conferma (torna quello di serie, se c'è). */
function remove(): void {
  const path = current.value?.path
  if (!path) return
  $q.dialog({ title: t('content.deleteTitle'), message: t('content.files.deleteConfirm', { path }), cancel: true, persistent: true }).onOk(async () => {
    try {
      await deleteFile(area.value, path)
      current.value = null
      text.value = original.value = ''
      await load()
      await bar.value?.validate()
    } catch (e) {
      $q.notify({ type: 'negative', message: await describeError(e) })
    }
  })
}

onMounted(load)
</script>
