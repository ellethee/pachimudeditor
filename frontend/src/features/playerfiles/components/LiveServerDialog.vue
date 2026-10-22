<template>
  <pachi-dialog ref="dialogRef" :title="t('playerFiles.live.server.title')" min-width="760px" max-width="95vw" @hide="onDialogHide()">
    <div data-testid="live-server-dialog">
      <q-banner v-if="error" rounded class="bg-negative text-white q-mb-sm" role="alert" data-testid="live-server-error">{{ error }}</q-banner>
      <q-banner v-if="message" rounded class="bg-positive text-white q-mb-sm" role="status" data-testid="live-server-message">
        {{ message }}
        <template v-if="createdFor" #action>
          <q-btn flat :label="t('playerFiles.liveInv.editCreated')" data-testid="live-load-edit" @click="editCreated()" />
        </template>
      </q-banner>
      <q-banner v-if="warning" rounded class="bg-warning text-black q-mb-sm" role="alert" data-testid="live-server-warning">{{ warning }}</q-banner>

      <q-tabs v-model="tab" dense align="left" class="text-primary" active-color="primary" indicator-color="primary" @update:model-value="onTab">
        <q-tab name="who" :label="t('playerFiles.live.server.tabs.who')" data-testid="live-tab-who" />
        <q-tab name="info" :label="t('playerFiles.live.server.tabs.info')" data-testid="live-tab-info" />
        <q-tab v-if="canWrite" name="zone" :label="t('playerFiles.live.server.tabs.zone')" data-testid="live-tab-zone" />
        <q-tab v-if="canWrite" name="load" :label="t('playerFiles.live.server.tabs.load')" data-testid="live-tab-load" />
        <q-tab v-if="canWrite" name="echo" :label="t('playerFiles.live.server.tabs.echo')" data-testid="live-tab-echo" />
      </q-tabs>
      <q-separator />
      <q-tab-panels v-model="tab" animated>
        <q-tab-panel name="who" class="q-px-none">
          <div class="row items-center q-mb-sm">
            <span class="text-body2">{{ t('playerFiles.live.server.whoCount', { n: who?.count ?? 0 }) }}</span>
            <q-space />
            <q-btn flat dense round :icon="mdiRefresh" :aria-label="t('playerFiles.reload')" data-testid="live-who-reload" @click="loadWho()" />
          </div>
          <q-markup-table dense flat bordered data-testid="live-who-table">
            <thead>
              <tr>
                <th class="text-left">{{ t('playerFiles.col.name') }}</th>
                <th class="text-left">{{ t('playerFiles.live.server.state') }}</th>
                <th class="text-right">{{ t('playerFiles.col.level') }}</th>
                <th class="text-right">{{ t('playerFiles.col.roomVnum') }}</th>
                <th class="text-right">{{ t('playerFiles.live.server.zone') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in who?.players ?? []" :key="p.name" :data-testid="`live-who-${p.name}`">
                <td>{{ p.name }}</td>
                <td>{{ stateLabel(p.state) }}</td>
                <td class="text-right">{{ p.level ?? '—' }}</td>
                <td class="text-right">{{ p.room ?? '—' }}</td>
                <td class="text-right">{{ p.zone ?? '—' }}</td>
              </tr>
              <tr v-if="!who?.players.length">
                <td colspan="5" class="text-grey">{{ t('playerFiles.empty') }}</td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-tab-panel>

        <q-tab-panel name="info" class="q-px-none">
          <q-markup-table v-if="info" dense flat bordered data-testid="live-info-table">
            <tbody>
              <tr>
                <th class="text-left">{{ t('playerFiles.live.server.mud') }}</th>
                <td data-testid="live-info-mud">{{ [info.mud.name, info.mud.version].filter(Boolean).join(' ') }}</td>
              </tr>
              <tr>
                <th class="text-left">{{ t('playerFiles.live.server.uptime') }}</th>
                <td data-testid="live-info-uptime">{{ info.uptimeS === null ? '—' : formatDuration(info.uptimeS) }}</td>
              </tr>
              <tr v-for="(value, key) in info.players" :key="`p-${key}`">
                <th class="text-left">{{ t(`playerFiles.live.server.players.${key}`) }}</th>
                <td>{{ value }}</td>
              </tr>
              <tr v-for="(value, key) in info.world" :key="`w-${key}`">
                <th class="text-left">{{ t(`playerFiles.live.server.world.${key}`) }}</th>
                <td>{{ value }}</td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-tab-panel>

        <q-tab-panel v-if="canWrite" name="zone" class="q-px-none">
          <p class="text-body2">{{ t('playerFiles.live.server.zoneHint') }}</p>
          <q-select
            v-model="zone"
            :options="zoneOptions"
            emit-value
            map-options
            dense
            outlined
            :label="t('playerFiles.live.server.zonePick')"
            data-testid="live-zone-select"
          />
          <q-checkbox v-model="onlyIfEmpty" :label="t('playerFiles.live.server.onlyIfEmpty')" data-testid="live-zone-empty" />
          <div>
            <q-btn color="primary" :label="t('playerFiles.live.server.zoneReset')" :disable="zone === null || busy" data-testid="live-zone-reset" @click="resetZone()" />
          </div>
        </q-tab-panel>

        <q-tab-panel v-if="canWrite" name="load" class="q-px-none">
          <q-btn-toggle
            v-model="loadKind"
            no-caps
            dense
            toggle-color="primary"
            :options="[
              { label: t('playerFiles.live.server.mob'), value: 'mob', 'data-testid': 'live-load-kind-mob' },
              { label: t('playerFiles.live.server.obj'), value: 'obj', 'data-testid': 'live-load-kind-obj' },
            ]"
          />
          <div class="row q-col-gutter-sm q-mt-xs">
            <div class="col-12 col-sm-4">
              <q-select
                v-model="loadPick"
                :options="loadFound"
                :label="loadKind === 'mob' ? t('playerFiles.live.server.pickMob') : t('playerFiles.live.server.pickObj')"
                use-input
                input-debounce="250"
                dense
                outlined
                option-label="label"
                data-testid="live-load-vnum"
                @filter="onFilterLoad"
              >
                <template #no-option>
                  <q-item><q-item-section class="text-grey">{{ t('playerFiles.live.server.pickNone') }}</q-item-section></q-item>
                </template>
              </q-select>
            </div>
            <div class="col-12 col-sm-4">
              <q-input v-model.number="loadCount" type="number" min="1" max="10" dense outlined :label="t('playerFiles.live.server.count')" data-testid="live-load-count" />
            </div>
          </div>
          <q-btn-toggle
            v-model="loadWhere"
            class="q-mt-sm"
            no-caps
            dense
            toggle-color="primary"
            :options="[
              { label: t('playerFiles.live.server.toRoom'), value: 'room', 'data-testid': 'live-load-where-room' },
              { label: t('playerFiles.live.server.toPlayer'), value: 'player', 'data-testid': 'live-load-where-player' },
            ]"
          />
          <q-select
            v-if="loadWhere === 'room'"
            v-model="loadRoomPick"
            :options="roomFound"
            :label="t('playerFiles.live.server.pickRoom')"
            use-input
            input-debounce="250"
            dense
            outlined
            class="q-mt-sm"
            option-label="label"
            data-testid="live-load-room"
            @filter="onFilterRoom"
          >
            <template #no-option>
              <q-item><q-item-section class="text-grey">{{ t('playerFiles.live.server.pickNone') }}</q-item-section></q-item>
            </template>
          </q-select>
          <q-select
            v-else
            v-model="loadPlayer"
            :options="playerOptions"
            dense
            outlined
            class="q-mt-sm"
            :label="t('playerFiles.live.server.player')"
            data-testid="live-load-player"
          />
          <q-banner v-if="loadKind === 'obj' && loadWhere === 'room' && inventoryLive" dense rounded class="bg-grey-3 text-black q-mt-sm" role="note" data-testid="live-load-room-note">
            {{ t('playerFiles.liveInv.roomObjectNote') }}
          </q-banner>
          <div class="q-mt-sm">
            <q-btn color="primary" :label="t('playerFiles.live.server.create')" :disable="busy || !loadPick" data-testid="live-load-go" @click="doLoad()" />
          </div>
        </q-tab-panel>

        <q-tab-panel v-if="canWrite" name="echo" class="q-px-none">
          <q-input v-model="echoText" type="textarea" autogrow dense outlined maxlength="400" counter :label="t('playerFiles.live.server.text')" data-testid="live-echo-text" />
          <q-btn-toggle
            v-model="echoWhere"
            class="q-mt-sm"
            no-caps
            dense
            toggle-color="primary"
            :options="[
              { label: t('playerFiles.live.server.toAll'), value: 'all', 'data-testid': 'live-echo-where-all' },
              { label: t('playerFiles.live.server.toPlayer'), value: 'player', 'data-testid': 'live-echo-where-player' },
              { label: t('playerFiles.live.server.toRoom'), value: 'room', 'data-testid': 'live-echo-where-room' },
            ]"
          />
          <q-select
            v-if="echoWhere === 'player'"
            v-model="echoPlayer"
            :options="playerOptions"
            dense
            outlined
            class="q-mt-sm"
            :label="t('playerFiles.live.server.player')"
            data-testid="live-echo-player"
          />
          <q-select
            v-if="echoWhere === 'room'"
            v-model="echoRoomPick"
            :options="roomFound"
            :label="t('playerFiles.live.server.pickRoom')"
            use-input
            input-debounce="250"
            dense
            outlined
            class="q-mt-sm"
            option-label="label"
            data-testid="live-echo-room"
            @filter="onFilterRoom"
          >
            <template #no-option>
              <q-item><q-item-section class="text-grey">{{ t('playerFiles.live.server.pickNone') }}</q-item-section></q-item>
            </template>
          </q-select>
          <div class="q-mt-sm">
            <q-btn color="primary" :label="t('playerFiles.live.server.send')" :disable="busy || !echoText.trim()" data-testid="live-echo-go" @click="sendEcho()" />
          </div>
        </q-tab-panel>
      </q-tab-panels>
    </div>
    <template #actions>
      <q-btn flat :label="t('playerFiles.close')" @click="onDialogCancel" />
    </template>
  </pachi-dialog>
</template>

<script setup lang="ts">
/**
 * Pannello «Server live»: giocatori connessi, stato del server, reset di una zona, creazione di mob/oggetti e messaggi. Le azioni di
 * scrittura compaiono solo se il MUD ha la classe `write` attiva e il mondo non è in sola lettura. Nessun ritentativo automatico:
 * un esito sconosciuto (timeout) lo dice il messaggio d'errore.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { mdiRefresh } from '@quasar/extras/mdi-v7'
import { PachiDialog } from '@ilpachi/pachi-kit/dialog'
import { describeError } from '../../players/helpers/describe-error'
import { useLive } from '../helpers/live-state'
import { formatDuration } from '../helpers/format'
import { listMobs } from '../../mobs/services/mobs-api'
import { listObjects } from '../../objects/services/objects-api'
import { searchRooms } from '../../rooms/services/rooms-api'
import { echoLive, getLiveInfo, getLiveInventory, getLiveWho, getLiveZones, loadLive, resetLiveZone } from '../services/live-api'
import LiveItemEditDialog from './LiveItemEditDialog.vue'
import type { ILiveInfo, ILiveWho, ILiveZone } from '../types/live'

defineEmits([...useDialogPluginComponent.emits])

const { t, te } = useI18n()
const $q = useQuasar()
const { dialogRef, onDialogHide, onDialogCancel } = useDialogPluginComponent()
const { canWrite, inventory: inventoryLive, canWriteInventory } = useLive()

/** Elemento scelto in un selettore filtrabile: `value` e' il vnum da inviare. */
interface PickOption {
  value: number
  label: string
}

const tab = ref('who')
const error = ref('')
const message = ref('')
const warning = ref('')
const busy = ref(false)
/** Oggetto appena creato per un giocatore: permette «Modifica» (solo con l'inventario live scrivibile). */
const createdFor = ref<{ player: string; vnum: number } | null>(null)
const who = ref<ILiveWho>()
const info = ref<ILiveInfo>()
const zones = ref<ILiveZone[]>([])
const zone = ref<number | null>(null)
const onlyIfEmpty = ref(false)
const loadKind = ref<'mob' | 'obj'>('mob')
const loadWhere = ref<'room' | 'player'>('room')
const loadPick = ref<PickOption | null>(null)
const loadFound = ref<PickOption[]>([])
const loadCount = ref(1)
const loadRoomPick = ref<PickOption | null>(null)
const roomFound = ref<PickOption[]>([])
const loadPlayer = ref<string | null>(null)
const echoText = ref('')
const echoWhere = ref<'all' | 'player' | 'room'>('all')
const echoPlayer = ref<string | null>(null)
const echoRoomPick = ref<PickOption | null>(null)

/** Zone nell'ordine del gioco, con l'indice da inviare. */
const zoneOptions = computed(() => zones.value.filter((z) => z.index > 0).map((z) => ({ label: `${z.name} (#${z.index})`, value: z.index })))
const playerOptions = computed(() => (who.value?.players ?? []).filter((p) => p.state === 'playing').map((p) => p.name))

/** Testo di uno stato di `who` (`playing|linkdead|polymorph`). */
function stateLabel(state: string): string {
  return te(`playerFiles.live.state.${state}`) ? t(`playerFiles.live.state.${state}`) : state
}

/**
 * Esegue un'azione mostrando il messaggio di successo o l'errore del backend (senza mai nascondere un esito sconosciuto).
 *
 * @param action - azione asincrona che restituisce il testo di conferma
 */
async function run(action: () => Promise<string>): Promise<void> {
  busy.value = true
  error.value = message.value = warning.value = ''
  createdFor.value = null
  try {
    message.value = await action()
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    busy.value = false
  }
}

/** Rilegge i giocatori connessi. */
async function loadWho(): Promise<void> {
  await run(async () => {
    who.value = await getLiveWho()
    return ''
  })
}

/** Carica i dati della scheda scelta. */
function onTab(name: string): void {
  if (name === 'who') void loadWho()
  if (name === 'info') void run(async () => ((info.value = await getLiveInfo()), ''))
  if (name === 'zone' && zones.value.length === 0) void run(async () => ((zones.value = await getLiveZones()), ''))
  if (name === 'load' || name === 'echo') void run(async () => ((who.value = await getLiveWho()), ''))
}

/** Reset della zona scelta, dopo conferma. */
function resetZone(): void {
  const chosen = zoneOptions.value.find((o) => o.value === zone.value)
  if (!chosen) return
  $q.dialog({
    title: t('playerFiles.live.server.zoneConfirmTitle'),
    message: t('playerFiles.live.server.zoneConfirm', { name: chosen.label }),
    persistent: true,
    ok: { label: t('playerFiles.live.server.zoneReset'), 'data-testid': 'live-zone-confirm' },
    cancel: { label: t('playerFiles.cancel'), flat: true },
  }).onOk(() => {
    void run(async () => {
      const out = await resetLiveZone(chosen.value, onlyIfEmpty.value)
      return out.executed ? t('playerFiles.live.server.zoneDone', { name: out.name }) : t('playerFiles.live.server.zoneSkipped', { name: out.name })
    })
  })
}

/**
 * Cerca mob o oggetti esistenti (secondo il tipo scelto) per nome o vnum.
 *
 * @param text - testo digitato
 * @param update - callback di q-select
 */
function onFilterLoad(text: string, update: (fn: () => void) => void): void {
  const search = loadKind.value === 'mob' ? listMobs({ search: text, pageSize: 20 }) : listObjects({ search: text, pageSize: 20 })
  void search
    .then((page) => page.items.map((e) => ({ value: e.vnum, label: `#${e.vnum} ${e.shortDescription}` })))
    .catch(() => [])
    .then((items) => update(() => (loadFound.value = items)))
}

/**
 * Cerca stanze esistenti per nome o vnum.
 *
 * @param text - testo digitato
 * @param update - callback di q-select
 */
function onFilterRoom(text: string, update: (fn: () => void) => void): void {
  void searchRooms(text)
    .then((rooms) => rooms.map((r) => ({ value: r.vnum, label: `#${r.vnum} ${r.name}` })))
    .catch(() => [])
    .then((items) => update(() => (roomFound.value = items)))
}

/** Crea mob o oggetti nella destinazione scelta. */
function doLoad(): void {
  const picked = loadPick.value
  if (!picked) return
  const target = loadWhere.value === 'room' ? { room: loadRoomPick.value?.value } : { player: loadPlayer.value ?? undefined }
  void run(async () => {
    const out = await loadLive(loadKind.value, { vnum: picked.value, count: loadCount.value, notify: false, ...target })
    const player = loadWhere.value === 'player' ? loadPlayer.value : null
    if (loadKind.value === 'obj' && player && canWriteInventory.value) createdFor.value = { player, vnum: picked.value }
    if (out.warnings.includes('vnum_not_saveable')) warning.value = t('playerFiles.liveInv.vnumNotSaveable', { vnum: picked.value })
    return t('playerFiles.live.server.created', { n: out.loaded.length })
  })
}

/**
 * Apre la modifica dell'oggetto appena creato per un giocatore: lo cerca nel suo inventario live (il primo oggetto portato con quel vnum,
 * perché il gioco mette i nuovi in testa). Gli oggetti creati in una stanza non sono indirizzabili dal canale.
 */
async function editCreated(): Promise<void> {
  const target = createdFor.value
  if (!target) return
  error.value = ''
  try {
    const inv = await getLiveInventory(target.player)
    const item = inv.items.find((i) => i.depth === 0 && i.slot === null && i.vnum === target.vnum)
    if (!item) {
      error.value = t('playerFiles.liveInv.createdNotFound')
      return
    }
    $q.dialog({ component: LiveItemEditDialog, componentProps: { playerName: target.player, itemRef: item.ref } })
  } catch (e) {
    error.value = await describeError(e)
  }
}

/** Manda il messaggio alla destinazione scelta. */
function sendEcho(): void {
  const to =
    echoWhere.value === 'all' ? { all: true } : echoWhere.value === 'player' ? { player: echoPlayer.value ?? undefined } : { room: echoRoomPick.value?.value }
  void run(async () => {
    const out = await echoLive({ text: echoText.value.trim(), ...to })
    return t('playerFiles.live.server.sent', { n: out.recipients })
  })
}

/** Cambiando tipo (mob/oggetto) la scelta precedente non vale piu'. */
watch(loadKind, () => {
  loadPick.value = null
  loadFound.value = []
})

onMounted(() => void loadWho())
</script>
