<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <h1 class="text-h5 q-my-none">{{ t('mobs.title') }}</h1>
      <q-select
        v-model="selectedZoneId"
        :options="zoneOptions"
        option-value="id"
        option-label="name"
        emit-value
        map-options
        :label="t('mobs.zone')"
        :loading="zonesLoading"
        style="min-width: 260px"
        dense
        outlined
      />
    </div>

    <list-filters v-if="ready && !loadError" v-model="filters" :controls="controls" />
    <pachi-error-state
      v-if="loadError"
      :title="t('mobs.errorTitle')"
      :description="t('mobs.errorDescription')"
      :primary-label="t('mobs.retry')"
      @primary="loadLookups"
    />
    <pachi-empty-state
      v-else-if="!zonesLoading && zones.length === 0"
      :icon="mdiInbox"
      :title="t('mobs.noZonesTitle')"
      :description="t('mobs.noZonesDescription')"
    />
    <pachi-table2
      v-else-if="ready"
      ref="table"
      :url="MOBS_URL"
      :columns="columns"
      :extra-params="extraParams"
      :initial-sort="[]"
      use-col-actions="emit-delete"
      :can-edit="allowRow"
      :can-delete="allowDelete"
      error-banner
      dense
      @pt2:edit-item="openEdit"
      @pt2:delete-item="confirmDelete"
      @row-dblclick="(_evt: Event, row: IMobs) => openEdit(row)"
    >
      <template #error="{ error, retry }">
        <table-error :error="error" :retry="retry" />
      </template>
      <template #body-cell-trainer="{ slotProps }">
        <q-td :props="slotProps">
          <q-chip v-if="slotProps.row.isTrainer" dense color="primary" text-color="white" :icon="mdiSchool" data-test="trainer-chip">
            {{ t('mobs.trainerChip') }}
          </q-chip>
        </q-td>
      </template>
      <template #toolbar-actions="{ api }">
        <columns-menu :names="columnNames" :model-value="visibleColumns" :label-of="columnLabel" @toggle="toggleColumn" @reset="resetColumns" />
        <q-btn v-if="!readOnly" color="primary" :icon="mdiPlus" :label="t('mobs.new')" @click="openCreate(api)" />
        <q-btn flat round :icon="mdiRefresh" :aria-label="t('mobs.reload')" @click="api.reload()" />
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiInbox, mdiPencil, mdiPlus, mdiRefresh, mdiSchool } from '@quasar/extras/mdi-v7'
import { PachiEmptyState, PachiErrorState } from '@ilpachi/pachifastquasar'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import type { PachiTable2Api, PachiTable2Exposed } from '@ilpachi/pachi-kit/table'
import { PachiEditDialog } from '@ilpachi/pachi-kit/edit-dialog'
import type { AwaitableData, ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import { describeError } from '../helpers/describe-error'
import InstancesSection from '../../instances/components/InstancesSection.vue'
import { applyDescriptors, enumNames } from '../../shared/helpers/descriptor-rows'
import { createExtraEditor } from '../../shared/helpers/extra-fields'
import { LOCKED_DIALOG_CLASS, guardOf, guardSection } from '../../shared/helpers/record-guard'
import { useWorld } from '../../shared/helpers/world-state'
import { whenReady } from '../../shared/helpers/when-ready'
import { localizeEnums } from '../../shared/helpers/enum-labels'
import { buildCombatRows, buildIdentityRows, buildRoleRows } from '../helpers/field-rows'
import {
  MOBS_URL,
  getEnums,
  getMob,
  getMobUsage,
  listClasses,
  listRaces,
  listZones,
  nextMobVnum,
} from '../services/mobs-api'
import type { IContentRef, IMobEnums, IMobs, IMobsInput, IZoneRef } from '../types/mobs'
import TableError from '../../shared/components/TableError.vue'
import ColumnsMenu from '../../shared/components/ColumnsMenu.vue'
import ListFilters from '../../shared/components/ListFilters.vue'
import ZonePickDialog from '../../shared/components/ZonePickDialog.vue'
import {
  emptyFilters,
  filterQueryKeys,
  filtersFromQuery,
  filtersToParams,
  loadColumns,
  saveColumns,
  summarize,
} from '../../shared/helpers/list-filters'
import type { IFilterControl, IListFilters } from '../../shared/helpers/list-filters'
import { COLUMNS_KEY, COLUMN_NAMES, FILTER_SPECS, RANGE_KEYS, defaultColumns } from '../helpers/list-query'

const { t, te } = useI18n()
const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const { readOnly, supports, fieldOf, extraFieldsOf, declaresExtra } = useWorld()

/** Tutte le righe si aprono in modifica (in sola lettura il form è bloccato); serve anche a tipizzare la tabella su `IMobs`. */
const allowRow = (_row: IMobs): boolean => true
/** Eliminabili solo in un mondo scrivibile. */
const allowDelete = (row: IMobs): boolean => !readOnly.value && !guardOf(row.extra).corrupted

const table = ref<PachiTable2Exposed<IMobs> | null>(null)
const zones = ref<IZoneRef[]>([])
const zonesLoading = ref(true)
const loadError = ref(false)
/** Valore del selettore di zona per «tutte le zone» (gli id reali sono >= 0). */
const ALL_ZONES = -1
const selectedZoneId = ref<number>(ALL_ZONES)
/** `true` a lookup caricati: la tabella può partire con zona e filtri letti dall'URL. */
const ready = ref(false)
const filters = ref<IListFilters>(emptyFilters(FILTER_SPECS))
const enums = ref<IMobEnums>()
/** Risposta grezza di `/api/meta/enums` (comprende anche le tabelle specifiche del mondo, es. `romMobFlags`). */
const enumsRaw = computed(() => enums.value as unknown as Record<string, unknown> | undefined)
const races = ref<IContentRef[]>([])
const classes = ref<IContentRef[]>([])

/** Opzioni del selettore: «Tutte le zone» e poi le zone. */
const zoneOptions = computed(() => [{ id: ALL_ZONES, name: t('mobs.allZones') }, ...zones.value])

/** Filtro per zona (se scelta) e filtri sulle statistiche inviati alla tabella. */
const extraParams = computed<Record<string, unknown>>(() => ({
  ...(selectedZoneId.value !== ALL_ZONES ? { zoneId: selectedZoneId.value } : {}),
  ...filtersToParams(FILTER_SPECS, filters.value),
}))

/** `true` se il mondo ha il campo del mob (un campo `unsupported` non ha colonna né filtro). */
function hasField(name: string): boolean {
  return !fieldOf('mob', name)?.unsupported
}

/** `true` se la colonna è disponibile: «Insegna» segue `isTrainer`, «Procedura speciale» esiste solo se il mondo dichiara `extra.specProc`. */
function hasColumn(name: string): boolean {
  if (name === 'trainer') return hasField('isTrainer')
  if (name === 'specProc') return extraFieldsOf('mob').some((field) => field.name === 'specProc')
  return hasField(name)
}

/** Controlli della barra dei filtri (testi, opzioni e campi non supportati nascosti). */
const controls = computed<IFilterControl[]>(() =>
  FILTER_SPECS.map((spec): IFilterControl => {
    const base = { ...spec, label: t(`mobs.filters.${spec.key}`), hidden: !hasField(spec.key) }
    if (spec.key === 'sex') return { ...base, options: (enums.value?.sex ?? []).map((o) => ({ value: o.value, label: o.label })) }
    if (spec.key === 'flags') {
      return { ...base, free: true, options: enumNames(enumsRaw.value, fieldOf('mob', 'flags')).map((n) => ({ value: n, label: n })) }
    }
    if (spec.key === 'raceId') return { ...base, options: races.value.map((r) => ({ value: r.id, label: r.name })) }
    if (spec.key === 'classId') return { ...base, options: classes.value.map((r) => ({ value: r.id, label: r.name })) }
    if (spec.key === 'trainer') return { ...base, hidden: !hasField('isTrainer') }
    return { ...base, label: columnLabel(spec.key) }
  }),
)

/** Colonne selezionabili in questo mondo (senza quelle dei campi che non ha). */
const columnNames = computed<string[]>(() => COLUMN_NAMES.filter((name) => hasColumn(name)))
/** Colonne visibili: scelta salvata dal viewer, altrimenti pochi default (telefono) o i principali. */
const visibleColumns = ref<string[]>(loadColumns(COLUMNS_KEY, COLUMN_NAMES) ?? defaultColumns($q.screen.lt.sm))

/**
 * Mostra o nasconde una colonna e salva la scelta.
 *
 * @param name - nome della colonna
 * @param on - `true` per mostrarla
 */
function toggleColumn(name: string, on: boolean): void {
  visibleColumns.value = COLUMN_NAMES.filter((column) => (column === name ? on : visibleColumns.value.includes(column)))
  saveColumns(COLUMNS_KEY, visibleColumns.value)
}

/** Ripristina le colonne di default. */
function resetColumns(): void {
  visibleColumns.value = defaultColumns($q.screen.lt.sm)
  saveColumns(COLUMNS_KEY, visibleColumns.value)
}

/**
 * Intestazione di una colonna.
 *
 * @param name - nome della colonna
 */
function columnLabel(name: string): string {
  return t(`mobs.columns.${name}`)
}

/**
 * Nome della zona.
 *
 * @param zoneId - id della zona
 */
function zoneName(zoneId: number): string {
  return zones.value.find((zone) => zone.id === zoneId)?.name ?? String(zoneId)
}

/**
 * Etichetta del sesso.
 *
 * @param sex - valore intero
 */
function sexLabel(sex: number): string {
  return enums.value?.sex.find((option) => option.value === sex)?.label ?? String(sex)
}

/**
 * Nome di un riferimento (razza/classe) dato l'id.
 *
 * @param refs - elenco dei riferimenti
 * @param id - id cercato
 */
function refName(refs: IContentRef[], id: string | null): string {
  return refs.find((ref) => ref.id === id)?.name ?? '—'
}

/** Tutte le colonne (il `name` è la chiave di `orderBy` del backend); mostrate solo quelle scelte e supportate. */
const allColumns = computed<QTableColumn<IMobs>[]>(() => {
  const num = (name: (typeof RANGE_KEYS)[number]): QTableColumn<IMobs> => ({
    name,
    label: columnLabel(name),
    field: name,
    align: 'right',
    sortable: true,
    format: (value: number | null) => (value === null || value === undefined ? '' : String(value)),
  })
  return [
    { name: 'vnum', label: columnLabel('vnum'), field: 'vnum', align: 'left', sortable: true },
    { name: 'shortDescription', label: columnLabel('shortDescription'), field: 'shortDescription', align: 'left', sortable: true },
    { name: 'zoneId', label: columnLabel('zoneId'), field: (row) => zoneName(row.zoneId), align: 'left', sortable: true },
    num('level'),
    { name: 'sex', label: columnLabel('sex'), field: (row) => sexLabel(row.sex), align: 'left', sortable: true },
    { name: 'raceId', label: columnLabel('raceId'), field: (row) => refName(races.value, row.raceId), align: 'left', sortable: true },
    { name: 'classId', label: columnLabel('classId'), field: (row) => refName(classes.value, row.classId), align: 'left', sortable: true },
    num('alignment'),
    num('armorClass'),
    num('thac0'),
    num('hpDiceCount'),
    num('hpDieSize'),
    num('hpBonus'),
    num('damageDiceCount'),
    num('damageDieSize'),
    num('damageBonus'),
    num('gold'),
    num('experience'),
    {
      name: 'flags',
      label: columnLabel('flags'),
      field: (row) => summarize(row.flags),
      align: 'left',
      style: 'max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap',
    },
    // non ordinabili: derivati (flag o procedura speciale), non colonne del database
    { name: 'trainer', label: columnLabel('trainer'), field: (row) => (row.isTrainer ? t('mobs.trainerChip') : ''), align: 'left' },
    { name: 'specProc', label: columnLabel('specProc'), field: (row) => String(row.extra?.specProc ?? ''), align: 'left' },
  ]
})
const columns = computed(() =>
  allColumns.value.filter((column) => visibleColumns.value.includes(column.name) && columnNames.value.includes(column.name)),
)

/** Carica zone, enum, razze e classi (una volta, alla creazione della pagina). */
async function loadLookups(): Promise<void> {
  loadError.value = false
  zonesLoading.value = true
  try {
    const [zoneList, enumList, raceList, classList] = await Promise.all([
      listZones(),
      getEnums(),
      listRaces(),
      listClasses(),
    ])
    zones.value = zoneList
    enums.value = localizeEnums(enumList)
    races.value = raceList
    classes.value = classList
    applyQuery()
  } catch {
    loadError.value = true
  } finally {
    zonesLoading.value = false
  }
  ready.value = !loadError.value
  if (!loadError.value) await openFromQuery()
}

/** Zona e filtri dall'URL (zona sconosciuta o assente: tutte le zone). */
function applyQuery(): void {
  const wanted = route.query.zoneId === undefined ? NaN : Number(route.query.zoneId)
  selectedZoneId.value = zones.value.find((zone) => zone.id === wanted)?.id ?? ALL_ZONES
  filters.value = filtersFromQuery(FILTER_SPECS, route.query)
}

/** Query string corrispondente allo stato (zona e filtri) mantenendo gli altri parametri dell'URL. */
function stateQuery(): Record<string, string> {
  const owned = filterQueryKeys(FILTER_SPECS)
  const base = Object.fromEntries(Object.entries(route.query).filter(([key]) => key !== 'zoneId' && !owned.includes(key))) as Record<
    string,
    string
  >
  const zone = selectedZoneId.value !== ALL_ZONES ? { zoneId: String(selectedZoneId.value) } : {}
  const entries = Object.entries(filtersToParams(FILTER_SPECS, filters.value, true)).map(([key, value]) => [key, String(value)])
  return { ...base, ...zone, ...Object.fromEntries(entries) }
}

/** Riscrive l'URL con lo stato corrente (sostituisce la voce di cronologia solo se qualcosa è cambiato). */
function syncUrl(): void {
  if (!ready.value) return
  const next = stateQuery()
  const same = JSON.stringify(Object.entries(next).sort()) === JSON.stringify(Object.entries(route.query).sort())
  if (!same) void router.replace({ path: route.path, query: next })
}

watch([selectedZoneId, filters], syncUrl, { deep: true })
// navigazione indietro/avanti o link condiviso: lo stato segue l'URL
watch(
  () => route.query,
  () => {
    if (!ready.value) return
    const parsed = filtersFromQuery(FILTER_SPECS, route.query)
    const zone = Number(route.query.zoneId)
    const nextZone = zones.value.some((z) => z.id === zone) ? zone : ALL_ZONES
    if (nextZone === selectedZoneId.value && JSON.stringify(parsed) === JSON.stringify(filters.value)) return
    applyQuery()
  },
)

/**
 * Deep-link `?mobId=`: seleziona la zona del mob e ne apre l'editor (poi toglie il parametro, così un
 * ricaricamento non riapre il dialog). Un id inesistente lascia semplicemente l'elenco.
 */
async function openFromQuery(): Promise<void> {
  const id = Number(route.query.mobId)
  if (route.query.mobId === undefined || !Number.isFinite(id)) return
  try {
    const mob = await getMob(id)
    if (zones.value.some((zone) => zone.id === mob.zoneId)) selectedZoneId.value = mob.zoneId
    const { mobId: _mobId, ...rest } = route.query
    await router.replace({ path: route.path, query: { ...rest, zoneId: String(mob.zoneId) } })
    const api = await whenReady(() => table.value?.api)
    await openDialog(api, mob)
  } catch {
    // mob inesistente o non leggibile: resta l'elenco
  }
}

/**
 * Valori iniziali del form per un nuovo mob.
 *
 * @param zoneId - zona di destinazione
 */
function emptyMob(zoneId: number): IMobsInput {
  return {
    vnum: 0,
    zoneId,
    keywords: '',
    shortDescription: '',
    longDescription: '',
    detailedDescription: '',
    level: 1,
    thac0: 20,
    armorClass: 0,
    hpDiceCount: 1,
    hpDieSize: 8,
    hpBonus: 0,
    damageDiceCount: 1,
    damageDieSize: 4,
    damageBonus: 0,
    gold: 0,
    experience: 0,
    sex: enums.value?.sex[0]?.value ?? 0,
    flags: [],
    raceId: null,
    classId: null,
    alignment: 0,
    debuffSkillId: null,
    shopId: null,
    questIds: [],
    isBanker: false,
    teachesClassIds: null,
    teachesSkillIds: null,
  }
}

/**
 * Apre il dialog di creazione/modifica.
 *
 * @param api - API della tabella (per salvare e ricaricare)
 * @param record - mob da modificare; assente per la creazione
 * @param createZoneId - zona del nuovo mob (solo creazione)
 */
async function openDialog(api: PachiTable2Api<IMobs>, record?: IMobs, createZoneId?: number): Promise<void> {
  const zoneId = record?.zoneId ?? createZoneId
  if (zoneId === undefined || zoneId === ALL_ZONES) return
  const initial: Record<string, unknown> = record ? { ...record } : { ...emptyMob(zoneId) }
  // le liste opzionali nulle si mostrano come vuote (chip/select multiplo)
  initial.questIds = initial.questIds ?? []
  initial.teachesClassIds = initial.teachesClassIds ?? []
  initial.teachesSkillIds = initial.teachesSkillIds ?? []
  if (!record) {
    // creazione: propone subito il prossimo vnum libero della zona (l'utente può cambiarlo)
    try {
      initial.vnum = await nextMobVnum(zoneId)
    } catch {
      // resta 0: il pulsante del campo vnum permette di riprovare
    }
  }
  const guard = guardOf(record?.extra)
  const locked = readOnly.value || guard.corrupted
  const lockRows = (rows: IFieldRow[]): IFieldRow[] =>
    guard.corrupted ? rows.map((row) => row.map((def) => ({ ...def, disable: true, readonly: true }))) : rows
  const rowsOf = (rows: IFieldRow[]): IFieldRow[] => lockRows(applyDescriptors(rows, 'mob', fieldOf, t))
  const extraEditor = createExtraEditor({
    t,
    te,
    descriptors: extraFieldsOf('mob'),
    declared: declaresExtra('mob'),
    readonly: locked,
    extra: record?.extra,
    enums: enumsRaw.value,
    order: 40,
  })
  const sections: ISectionDefinition[] = [
    {
      key: 'identity',
      title: t('mobs.sections.identity'),
      component: markRaw(FieldsSection),
      props: { rows: rowsOf(buildIdentityRows(t, zoneId, !!record)) },
      initialValue: initial,
      order: 10,
      container: { type: 'card', flat: true, bordered: true, class: 'q-pa-md q-mb-md' },
    },
    {
      key: 'combat',
      title: t('mobs.sections.combat'),
      component: markRaw(FieldsSection),
      props: {
        rows: rowsOf(
          buildCombatRows(t, enums.value, races.value, classes.value, enumNames(enumsRaw.value, fieldOf('mob', 'flags'))),
        ),
      },
      initialValue: initial,
      order: 20,
      container: { type: 'expansion', title: t('mobs.sections.combat'), defaultOpened: true },
    },
    {
      key: 'roles',
      title: t('mobs.sections.roles'),
      component: markRaw(FieldsSection),
      props: { rows: rowsOf(buildRoleRows(t, classes.value)) },
      initialValue: initial,
      order: 30,
      container: { type: 'expansion', title: t('mobs.sections.roles'), defaultOpened: false },
    },
  ]
  if (extraEditor) sections.push(extraEditor.section)
  const banner = guardSection(guard)
  if (banner) sections.unshift(banner)
  if (record && supports('supportsInstances') && !guard.corrupted) {
    sections.push({
      key: 'instances',
      title: t('worlds.instances'),
      component: markRaw(InstancesSection),
      props: { kind: 'mob', prototypeId: record.id },
      initialValue: {},
      order: 50,
      container: { type: 'expansion', title: t('worlds.instances'), defaultOpened: false },
    })
  }
  $q.dialog({
    component: PachiEditDialog,
    componentProps: {
      title: record ? t('mobs.editTitle') : t('mobs.createTitle'),
      icon: record ? mdiPencil : mdiPlus,
      sections,
      avoidHideWithChanges: true,
      commonProps: locked ? { readonly: true } : {},
      cardClass: guard.corrupted ? LOCKED_DIALOG_CLASS : '',
      width: '720px',
      maxWidth: '95vw',
    },
  }).onOk(async ({ data, onSuccess, onError }: AwaitableData) => {
    if (locked) {
      onError(new Error(t('worlds.readOnlyHint')))
      return
    }
    const body = {
      ...(data.sections.identity as Record<string, unknown>),
      ...(data.sections.combat as Record<string, unknown>),
      ...(data.sections.roles as Record<string, unknown>),
    } as Partial<IMobsInput>
    // campi opzionali: stringa vuota -> null; liste di insegnamento vuote -> null
    if (!body.shopId) body.shopId = null
    if (!body.debuffSkillId) body.debuffSkillId = null
    if (!body.teachesClassIds?.length) body.teachesClassIds = null
    if (!body.teachesSkillIds?.length) body.teachesSkillIds = null
    // `extra` (campi specifici del mondo) solo con le chiavi cambiate
    const extra = extraEditor?.collect(data.sections.extra)
    if (extra) body.extra = extra
    try {
      if (record) {
        // PUT = patch parziale: il vnum e la zona non si cambiano
        const { vnum: _vnum, ...patch } = body
        await api.Put<IMobs>(`/${record.id}`, patch, { cacheFor: 0, meta: { autoError: false } })
        await api.reload()
      } else {
        // POST senza slash finale (createRecord della tabella posterebbe su `{url}/`, che il backend non espone)
        await api.Post<IMobs>('', { ...initial, ...body, zoneId }, { cacheFor: 0, meta: { autoError: false } })
        await api.reload()
      }
      onSuccess()
    } catch (error) {
      onError(new Error(await describeError(error)))
    }
  })
}

/** Gestore dell'edit della tabella (pulsante riga o doppio click). */
function openEdit(row: IMobs, api?: PachiTable2Api<IMobs>): void {
  const tableApi = api ?? table.value?.api
  if (tableApi) openDialog(tableApi, row)
}

/** Apre il dialog di creazione: con «Tutte le zone» chiede prima la zona di destinazione. */
function openCreate(api: PachiTable2Api<IMobs>): void {
  if (selectedZoneId.value !== ALL_ZONES) {
    void openDialog(api, undefined, selectedZoneId.value)
    return
  }
  $q.dialog({ component: ZonePickDialog, componentProps: { zones: zones.value, scope: 'mobs' } }).onOk((zoneId: number) => {
    void openDialog(api, undefined, zoneId)
  })
}

/**
 * Chiede conferma (segnalando i reset che lo referenziano) e elimina il mob.
 *
 * @param row - mob da eliminare
 * @param api - API della tabella
 */
async function confirmDelete(row: IMobs, api: PachiTable2Api<IMobs>): Promise<void> {
  const usage = await getMobUsage(row.id)
  const zoneNames = [...new Set(usage.map((item) => item.zoneName))].join(', ')
  const warning =
    usage.length > 0 ? ' ' + t('mobs.delete.usageWarning', { count: usage.length, zones: zoneNames }) : ''
  $q.dialog({
    title: t('mobs.delete.title'),
    message: t('mobs.delete.message', { name: row.shortDescription, vnum: row.vnum }) + warning,
    cancel: true,
  }).onOk(() => {
    // gli errori (es. 409 in uso nei reset) li mostra già il dialog globale dell'HTTP client
    api.deleteRecord(row).catch(() => undefined)
  })
}

onMounted(loadLookups)
</script>
