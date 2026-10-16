<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <h1 class="text-h5 q-my-none">{{ t('mobs.title') }}</h1>
      <q-select
        v-model="selectedZoneId"
        :options="zones"
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
      v-else-if="selectedZoneId !== undefined"
      ref="table"
      :url="MOBS_URL"
      :columns="columns"
      :extra-params="extraParams"
      :initial-sort="[{ column: 'vnum', direction: 'asc' }]"
      use-col-actions="emit-delete"
      :can-edit="allowRow"
      :can-delete="allowDelete"
      error-banner
      dense
      @pt2:edit-item="openEdit"
      @pt2:delete-item="confirmDelete"
      @row-dblclick="(_evt: Event, row: IMobs) => openEdit(row)"
    >
      <template #toolbar-actions="{ api }">
        <q-btn v-if="!readOnly" color="primary" :icon="mdiPlus" :label="t('mobs.new')" @click="openCreate(api)" />
        <q-btn flat round :icon="mdiRefresh" :aria-label="t('mobs.reload')" @click="api.reload()" />
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiInbox, mdiPencil, mdiPlus, mdiRefresh } from '@quasar/extras/mdi-v7'
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
const selectedZoneId = ref<number>()
const enums = ref<IMobEnums>()
/** Risposta grezza di `/api/meta/enums` (comprende anche le tabelle specifiche del mondo, es. `romMobFlags`). */
const enumsRaw = computed(() => enums.value as unknown as Record<string, unknown> | undefined)
const races = ref<IContentRef[]>([])
const classes = ref<IContentRef[]>([])

/** Filtro esatto per zona inviato alla tabella. */
const extraParams = computed<Record<string, unknown>>(() =>
  selectedZoneId.value !== undefined ? { zoneId: selectedZoneId.value } : {},
)

/**
 * Nome di un riferimento (razza/classe) dato l'id.
 *
 * @param refs - elenco dei riferimenti
 * @param id - id cercato
 */
function refName(refs: IContentRef[], id: string | null): string {
  return refs.find((ref) => ref.id === id)?.name ?? '—'
}

const columns = computed<QTableColumn<IMobs>[]>(() => [
  { name: 'vnum', label: t('mobs.columns.vnum'), field: 'vnum', align: 'left', sortable: true },
  {
    name: 'shortDescription',
    label: t('mobs.columns.shortDescription'),
    field: 'shortDescription',
    align: 'left',
  },
  { name: 'level', label: t('mobs.columns.level'), field: 'level', align: 'left', sortable: true },
  {
    name: 'raceId',
    label: t('mobs.columns.race'),
    field: (row: IMobs) => refName(races.value, row.raceId),
    align: 'left',
  },
  {
    name: 'classId',
    label: t('mobs.columns.class'),
    field: (row: IMobs) => refName(classes.value, row.classId),
    align: 'left',
  },
])

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
    const wanted = Number(route.query.zoneId)
    selectedZoneId.value =
      zoneList.find((zone) => zone.id === wanted)?.id ?? selectedZoneId.value ?? zoneList[0]?.id
  } catch {
    loadError.value = true
  } finally {
    zonesLoading.value = false
  }
  if (!loadError.value) await openFromQuery()
}

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
    await router.replace({ path: route.path, query: { zoneId: String(mob.zoneId) } })
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
 */
async function openDialog(api: PachiTable2Api<IMobs>, record?: IMobs): Promise<void> {
  const zoneId = record?.zoneId ?? selectedZoneId.value
  if (zoneId === undefined) return
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

/** Apre il dialog di creazione. */
function openCreate(api: PachiTable2Api<IMobs>): void {
  openDialog(api)
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
    persistent: true,
  }).onOk(() => {
    // gli errori (es. 409 in uso nei reset) li mostra già il dialog globale dell'HTTP client
    api.deleteRecord(row).catch(() => undefined)
  })
}

onMounted(loadLookups)
</script>
