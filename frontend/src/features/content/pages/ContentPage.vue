<template>
  <div class="q-pa-md column q-gutter-y-md">
    <restart-banner ref="banner" />

    <q-table
      flat
      bordered
      dense
      row-key="file"
      :rows="rows"
      :columns="columns"
      :loading="loading"
      :filter="filter"
      :pagination="{ rowsPerPage: 25, sortBy: 'name' }"
      :rows-per-page-options="[10, 25, 50, 0]"
      :no-data-label="t('content.empty')"
    >
      <template #top>
        <q-btn color="primary" no-caps :icon="mdiPlus" :label="t(`content.${kind}.create`)" @click="openCreate" />
        <q-btn flat round :icon="mdiRefresh" :aria-label="t('content.reload')" @click="load" />
        <q-space />
        <q-input v-model="filter" dense outlined clearable :placeholder="t('content.search')" style="min-width: 220px">
          <template #prepend><q-icon :name="mdiMagnify" /></template>
        </q-input>
      </template>

      <template #body-cell-status="{ row }">
        <q-td class="text-center">
          <q-badge v-if="!row.valid" color="negative" :label="t('content.status.invalid')">
            <q-tooltip>{{ row.error }}</q-tooltip>
          </q-badge>
          <q-badge v-else-if="row.disabled" color="grey" :label="t('content.status.disabled')" />
          <q-badge v-else color="positive" outline :label="t('content.status.active')" />
        </q-td>
      </template>

      <template #body-cell-actions="{ row }">
        <q-td class="text-right" auto-width>
          <q-btn dense flat round :icon="mdiPencil" :disable="!row.valid" @click="openEdit(row)">
            <q-tooltip>{{ t('content.actions.edit') }}</q-tooltip>
          </q-btn>
          <q-btn dense flat round :icon="row.disabled ? mdiPlayCircleOutline : mdiPauseCircleOutline" :disable="!row.valid" @click="toggleDisabled(row)">
            <q-tooltip>{{ row.disabled ? t('content.actions.enable') : t('content.actions.disable') }}</q-tooltip>
          </q-btn>
          <q-btn dense flat round color="negative" :icon="mdiDelete" @click="confirmDelete(row)">
            <q-tooltip>{{ t('content.actions.delete') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </q-table>
  </div>
</template>

<script setup lang="ts">
/**
 * Elenco e modifica di razze o classi (file YAML in `definitions/`). Una sola pagina per i due tipi:
 * cambia solo `kind`. Dopo ogni modifica il banner ricorda che serve il riavvio del game server.
 */
import { computed, markRaw, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import {
  mdiDelete,
  mdiMagnify,
  mdiPauseCircleOutline,
  mdiPencil,
  mdiPlayCircleOutline,
  mdiPlus,
  mdiRefresh,
} from '@quasar/extras/mdi-v7'
import { PachiEditDialog } from '@ilpachi/pachi-kit/edit-dialog'
import type { AwaitableData, ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import RestartBanner from '../components/RestartBanner.vue'
import { createContent, deleteContent, getContentOptions, listContent, setContentDisabled, updateContent } from '../services/content-api'
import { describeError } from '../helpers/describe-error'
import {
  buildClassCombatRows,
  buildClassGeneralRows,
  buildRaceFlagRows,
  buildRaceGeneralRows,
  buildRaceStatRows,
  formToClass,
  formToRace,
  raceToForm,
} from '../helpers/field-rows'
import type { ContentKind, IClass, IContentItem, IContentOptions, IRace } from '../types/content'

const props = defineProps<{ kind: ContentKind }>()

const { t } = useI18n()
const $q = useQuasar()

const rows = ref<IContentItem[]>([])
const loading = ref(false)
const filter = ref('')
const banner = ref<InstanceType<typeof RestartBanner> | null>(null)
let options: IContentOptions | null = null

/** Colonne: comuni (id, nome, stato, mob) più alcune specifiche del tipo. */
const columns = computed<QTableColumn<IContentItem>[]>(() => {
  const common: QTableColumn<IContentItem>[] = [
    { name: 'id', label: t('content.columns.id'), field: (r) => idOf(r), align: 'left', sortable: true },
    { name: 'name', label: t('content.columns.name'), field: 'name', align: 'left', sortable: true },
  ]
  const specific: QTableColumn<IContentItem>[] =
    props.kind === 'races'
      ? [
          { name: 'mobOnly', label: t('content.columns.mobOnly'), field: (r) => ((r as IRace).mobOnly ? t('content.yes') : t('content.no')), align: 'left' },
          { name: 'size', label: t('content.columns.size'), field: (r) => (r as IRace).size ?? '', align: 'left', sortable: true },
        ]
      : [
          { name: 'attrPrime', label: t('content.columns.attrPrime'), field: (r) => (r as IClass).attrPrime, align: 'left' },
          { name: 'hp', label: t('content.columns.hp'), field: (r) => `${(r as IClass).hpMin}-${(r as IClass).hpMax}`, align: 'left' },
        ]
  return [
    ...common,
    ...specific,
    { name: 'mobCount', label: t('content.columns.mobCount'), field: 'mobCount', align: 'right', sortable: true },
    { name: 'status', label: t('content.columns.status'), field: 'disabled', align: 'center' },
    { name: 'actions', label: '', field: 'file', align: 'right' },
  ]
})

/** Id dell'elemento (razza o classe). */
function idOf(item: IContentItem): string {
  return 'raceId' in item ? item.raceId : item.classId
}

/** Carica l'elenco dal backend. */
async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await listContent<IContentItem>(props.kind)
  } catch (error) {
    $q.notify({ type: 'negative', message: await describeError(error) })
  } finally {
    loading.value = false
  }
}

/** Opzioni dei form, caricate una volta sola. */
async function ensureOptions(): Promise<IContentOptions> {
  options ??= await getContentOptions()
  return options
}

/** Dopo una modifica riuscita: ricarica elenco e banner. */
async function afterChange(message: string): Promise<void> {
  await load()
  await banner.value?.refresh()
  $q.notify({ type: 'positive', message })
}

/**
 * Apre il dialogo di creazione/modifica.
 * @param initial elemento da modificare, o `null` per una nuova voce
 */
async function openDialog(initial: IContentItem | null): Promise<void> {
  const opts = await ensureOptions()
  const editing = initial !== null
  const isRace = props.kind === 'races'
  const sections: ISectionDefinition[] = isRace
    ? [
        section('general', t('content.races.sections.general'), buildRaceGeneralRows(t, opts, editing), 10),
        section('flags', t('content.races.sections.flags'), buildRaceFlagRows(t, opts), 20),
        section('stats', t('content.races.sections.stats'), buildRaceStatRows(t), 30),
      ]
    : [
        section('general', t('content.classes.sections.general'), buildClassGeneralRows(t, opts, editing), 10),
        section('combat', t('content.classes.sections.combat'), buildClassCombatRows(t), 20),
      ]
  const initialState = isRace
    ? raceToForm((initial as IRace | null) ?? { mobOnly: true, size: 'MEDIUM', description: '' })
    : { attrsPriority: [], attrPrime: '', thac000: 0, thac032: 0, hpMin: 0, hpMax: 0, weapon: 0, skillAdept: 0, ...(initial ?? {}) }
  for (const s of sections) s.initialValue = initialState
  $q.dialog({
    component: PachiEditDialog,
    componentProps: {
      title: t(`content.${props.kind}.${editing ? 'editTitle' : 'createTitle'}`),
      icon: editing ? mdiPencil : mdiPlus,
      sections,
      avoidHideWithChanges: true,
      width: '760px',
      maxWidth: '95vw',
    },
  }).onOk(async ({ data, onSuccess, onError }: AwaitableData) => {
    const merged = Object.assign({}, ...Object.values(data.sections)) as Record<string, unknown>
    try {
      const body = isRace ? formToRace({ ...merged, stats: initialState.stats, maxStats: initialState.maxStats }) : formToClass(merged)
      if (editing) await updateContent(props.kind, idOf(initial), body)
      else await createContent(props.kind, body)
      onSuccess()
      await afterChange(t('content.saved'))
    } catch (error) {
      onError(new Error(await describeError(error)))
    }
  })
}

/**
 * Costruisce la definizione di una sezione del dialogo.
 * @param key chiave della sezione
 * @param title titolo
 * @param sectionRows righe di campi
 * @param order posizione
 */
function section(key: string, title: string, sectionRows: IFieldRow[], order: number): ISectionDefinition {
  return {
    key,
    title,
    component: markRaw(FieldsSection),
    props: { rows: sectionRows },
    initialValue: {},
    order,
    container: { type: 'card', flat: true, bordered: true, class: 'q-pa-md q-mb-md', style: 'flex: none' },
  }
}

/** Apre la creazione. */
function openCreate(): void {
  void openDialog(null)
}

/** Apre la modifica di una riga. */
function openEdit(row: IContentItem): void {
  void openDialog(row)
}

/** Disattiva o riattiva (rinomina del file). */
async function toggleDisabled(row: IContentItem): Promise<void> {
  try {
    await setContentDisabled(props.kind, idOf(row), !row.disabled)
    await afterChange(t(row.disabled ? 'content.enabled' : 'content.disabledDone'))
  } catch (error) {
    $q.notify({ type: 'negative', message: await describeError(error) })
  }
}

/** Elimina dopo conferma; 409 se usato da mob (messaggio dal backend con il conteggio). */
function confirmDelete(row: IContentItem): void {
  $q.dialog({
    title: t('content.deleteTitle'),
    message: t(`content.${props.kind}.deleteConfirm`, { name: row.name, id: idOf(row), count: row.mobCount }),
    cancel: { label: t('content.cancel'), flat: true },
    ok: { label: t('content.actions.delete'), color: 'negative', flat: true },
    persistent: true,
  }).onOk(async () => {
    try {
      await deleteContent(props.kind, idOf(row))
      await afterChange(t('content.deleted'))
    } catch (error) {
      $q.notify({ type: 'negative', message: await describeError(error), timeout: 8000 })
    }
  })
}

onMounted(load)
</script>
