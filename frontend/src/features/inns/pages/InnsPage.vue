<template>
  <div class="q-pa-md column q-gutter-y-md">
    <div class="row items-center q-gutter-sm">
      <q-input v-model="search" dense outlined clearable debounce="150" class="col-12 col-sm-5 col-md-4" :label="t('inns.search')" data-testid="inns-search">
        <template #prepend><q-icon :name="mdiMagnify" /></template>
      </q-input>
      <q-toggle v-model="problemsOnly" :label="t('inns.onlyProblems')" data-testid="inns-problems-only" />
      <q-space />
      <q-btn v-if="!readOnly" outline no-caps color="primary" :icon="mdiPlus" :label="t('inns.create')" data-testid="inn-create" @click="openCreate" />
      <q-btn
        v-if="canValidate"
        outline
        no-caps
        color="primary"
        :icon="mdiClipboardCheckOutline"
        :label="t('content.live.validate')"
        :loading="busy"
        data-testid="inns-validate"
        @click="validate"
      />
      <q-btn flat no-caps :icon="mdiRefresh" :label="t('content.reload')" :loading="loading" data-testid="inns-refresh" @click="load" />
    </div>
    <q-banner v-if="error" rounded class="bg-negative text-white" data-testid="inns-error">{{ error }}</q-banner>
    <content-problems-panel />

    <pachi-table2 row-key="vnum" :rows="rows" :columns="columns" :loading="loading" single-sort :initial-sort="[]" dense :no-data-label="t('inns.empty')" data-testid="inns-table">
      <template #body="{ slotProps: p }">
        <q-tr :props="p" class="cursor-pointer" data-testid="inn-row" @click="open(p.row)">
          <q-td key="vnum" :props="p">{{ p.row.vnum }}</q-td>
          <q-td key="name" :props="p">{{ p.row.name }}</q-td>
          <q-td key="zone" :props="p">{{ p.row.zoneName }}</q-td>
          <q-td key="rooms" :props="p">
            <span v-for="(room, i) in p.row.rooms" :key="room.vnum" :class="room.name === null ? 'text-negative' : ''">
              {{ i ? ', ' : '' }}#{{ room.vnum }} {{ room.name ?? t('inns.missingRoom') }}
            </span>
          </q-td>
          <q-td key="status" :props="p">
            <q-badge v-if="!p.row.rooms.length" color="warning" text-color="dark" data-testid="inn-nospawn-badge">
              {{ t('inns.noSpawn') }}
              <q-tooltip>{{ t('inns.noSpawnHint') }}</q-tooltip>
            </q-badge>
            <q-badge v-else-if="hasMissingRoom(p.row)" color="negative" data-testid="inn-missing-room-badge">{{ t('inns.missingRoom') }}</q-badge>
            <span v-else class="text-positive">{{ t('inns.ok') }}</span>
          </q-td>
          <q-td key="actions" :props="p" auto-width>
            <q-btn
              v-if="canReload"
              flat
              round
              dense
              :icon="mdiReload"
              :aria-label="t('inns.reloadZone')"
              data-testid="inn-reload-zone"
              @click.stop="reloadZone(p.row)"
            >
              <q-tooltip>{{ t('inns.reloadZone') }}</q-tooltip>
            </q-btn>
          </q-td>
        </q-tr>
      </template>
    </pachi-table2>

    <q-dialog v-model="creating">
      <q-card style="min-width: 360px" data-testid="inn-create-dialog">
        <q-card-section class="text-h6">{{ t('inns.createTitle') }}</q-card-section>
        <q-card-section class="column q-gutter-y-md">
          <div class="text-caption">{{ t('inns.createHint') }}</div>
          <q-select v-model="zoneId" outlined dense emit-value map-options :options="zoneOptions" :label="t('inns.zone')" data-testid="inn-create-zone" @update:model-value="loadVnum" />
          <q-input v-model.number="newVnum" outlined dense type="number" :label="t('inns.vnum')" data-testid="inn-create-vnum" />
          <q-input v-model="newName" outlined dense :label="t('inns.name')" data-testid="inn-create-name" />
          <q-select
            v-model="room"
            outlined
            dense
            clearable
            use-input
            input-debounce="200"
            :options="roomOptions"
            :option-label="(r: IRoom) => `#${r.vnum} — ${r.name}`"
            :label="t('inns.room')"
            :hint="t('inns.roomHint')"
            data-testid="inn-create-room"
            @filter="filterRooms"
          />
          <q-banner v-if="createError" dense rounded class="bg-negative text-white" data-testid="inn-create-error">{{ createError }}</q-banner>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn v-close-popup flat no-caps :label="t('inns.cancel')" />
          <q-btn color="primary" no-caps :label="t('inns.confirm')" :loading="saving" :disable="zoneId === null || !newName.trim()" data-testid="inn-create-confirm" @click="create" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * Elenco di tutte le locande del gioco (i mob con `receptionist: true`) con ricerca. Segnala i locandieri che nessun reset carica
 * (o che puntano a una stanza inesistente): senza stanza `offer` e `rent` non funzionano. Un clic apre il mob; «Nuovo locandiere»
 * crea un mob receptionist da template.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import { mdiClipboardCheckOutline, mdiMagnify, mdiPlus, mdiRefresh, mdiReload } from '@quasar/extras/mdi-v7'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import ContentProblemsPanel from '../../content/components/ContentProblemsPanel.vue'
import { useContentLive } from '../../content/composables/use-content-live'
import { describeError } from '../../content/helpers/describe-error'
import { listZones, nextMobVnum } from '../../mobs/services/mobs-api'
import { useLive } from '../../playerfiles/helpers/live-state'
import { searchRooms } from '../../rooms/services/rooms-api'
import type { IRoom } from '../../rooms/types/rooms'
import type { IZoneRef } from '../../mobs/types/mobs'
import { useWorld } from '../../shared/helpers/world-state'
import { createInnkeeper, listInns } from '../services/inns-api'
import type { IInnItem } from '../types/inns'

const { t } = useI18n()
const $q = useQuasar()
const router = useRouter()
const { capabilities, readOnly } = useWorld()
const live = useLive()
const { busy, canValidate, validate, reloadZone: reloadZoneLive, refreshStatus } = useContentLive()

/** «Ricarica zona»: canale live connesso, scrittura consentita e comando `zone.reload` dichiarato dal gioco. */
const canReload = computed(() => live.canWrite.value && (live.status.value?.commands ?? []).includes('zone.reload'))

const inns = ref<IInnItem[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const problemsOnly = ref(false)

const creating = ref(false)
const zones = ref<IZoneRef[]>([])
const zoneId = ref<number | null>(null)
const newVnum = ref(0)
const newName = ref('')
const createError = ref('')
const saving = ref(false)
const room = ref<IRoom | null>(null)
const roomOptions = ref<IRoom[]>([])

const zoneOptions = computed(() => zones.value.map((z) => ({ value: z.id, label: `${z.name} (#${z.vnum})` })))

/** `true` se una stanza in cui un reset lo carica non esiste. */
function hasMissingRoom(row: IInnItem): boolean {
  return row.rooms.some((r) => r.name === null)
}

/** Righe filtrate per ricerca (mob, zona, stanze) e, se richiesto, per i soli locandieri con problemi. */
const rows = computed(() => {
  const needle = (search.value ?? '').trim().toLowerCase()
  return inns.value.filter((s) => {
    if (problemsOnly.value && s.rooms.length && !hasMissingRoom(s)) return false
    if (!needle) return true
    return [s.vnum, s.name, s.zoneName, ...s.rooms.map((r) => `${r.vnum} ${r.name ?? ''}`)].join(' ').toLowerCase().includes(needle)
  })
})

const columns = computed(() =>
  (['vnum', 'name', 'zone', 'rooms', 'status', 'actions'] as const).map((name) => ({
    name,
    label: name === 'actions' ? '' : t(`inns.columns.${name}`),
    field: name,
    align: 'left' as const,
  })),
)

/** Apre il mob (nel gioco `id == vnum`). */
function open(row: IInnItem): void {
  void router.push(`/mobs/${row.vnum}`)
}

/** Carica l'elenco. */
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    inns.value = await listInns()
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    loading.value = false
  }
}

/** Cerca le stanze mentre si digita (per nome o vnum). */
function filterRooms(value: string, update: (fn: () => void) => void): void {
  void searchRooms(value).then((found) => update(() => (roomOptions.value = found)))
}

/** Chiede al gioco acceso di rileggere dai file la zona del locandiere (errori: live non disponibile, sola lettura, ricarica fallita). */
async function reloadZone(row: IInnItem): Promise<void> {
  await reloadZoneLive(row.zoneId)
}

/** Propone il prossimo vnum libero della zona scelta. */
async function loadVnum(): Promise<void> {
  if (zoneId.value === null) return
  try {
    newVnum.value = await nextMobVnum(zoneId.value)
  } catch {
    // resta il valore corrente: il campo è modificabile a mano
  }
}

/** Apre il dialogo di creazione. */
async function openCreate(): Promise<void> {
  createError.value = ''
  room.value = null
  newName.value = t('inns.defaultName')
  creating.value = true
  if (!zones.value.length) zones.value = await listZones()
  if (zoneId.value === null && zones.value.length) zoneId.value = zones.value[0]!.id
  await loadVnum()
}

/** Crea il locandiere e apre il suo mob. */
async function create(): Promise<void> {
  if (zoneId.value === null) return
  saving.value = true
  createError.value = ''
  try {
    const { vnum, spawnedInZoneId, spawnError } = await createInnkeeper(
      zoneId.value,
      newVnum.value,
      newName.value.trim(),
      room.value ? { vnum: room.value.vnum, zoneId: room.value.zoneId } : null,
    )
    creating.value = false
    $q.notify({ type: 'positive', message: t('inns.created', { vnum }) })
    if (spawnedInZoneId !== null && spawnedInZoneId !== zoneId.value) $q.notify({ type: 'info', message: t('inns.spawnOtherZone') })
    if (spawnError) $q.notify({ type: 'warning', message: t('inns.spawnFailed', { error: spawnError }) })
    await load()
    void router.push(`/mobs/${vnum}`)
  } catch (e) {
    createError.value = await describeError(e)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  void load()
  if (!capabilities.value?.supportsLive) return // senza canale live niente richieste (il mondo risponde 409)
  await refreshStatus()
  void validate()
})
</script>
