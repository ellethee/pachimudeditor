<template>
  <pachi-dialog
    ref="dialogRef"
    :title="t('playerFiles.detail.title', { name: playerName })"
    min-width="720px"
    max-width="95vw"
    @hide="onDialogHide()"
  >
    <div data-testid="player-detail">
      <q-banner v-if="error" rounded class="bg-negative text-white q-mb-sm">{{ error }}</q-banner>
      <q-banner v-if="detail?.problem" rounded class="bg-negative text-white q-mb-sm" data-testid="player-detail-problem">
        {{ problemLabel(detail.problem) }}
      </q-banner>
      <q-banner v-if="!canWrite" rounded class="bg-grey-3 text-black q-mb-sm" role="note" data-testid="player-readonly-note">
        {{ t('playerFiles.detail.readOnly') }}
      </q-banner>
      <q-banner v-else rounded class="bg-grey-3 text-black q-mb-sm" role="note" data-testid="player-write-note">
        {{ t('playerFiles.detail.writable') }}
      </q-banner>
      <q-banner v-if="detail?.online === true" rounded class="bg-blue-1 text-black q-mb-sm" role="note" data-testid="player-online-note">
        {{ liveEditable ? t('playerFiles.live.detail.connectedLive') : t('playerFiles.live.detail.connectedFile') }}
      </q-banner>
      <q-banner v-if="canWrite && status?.serverRunning" rounded class="bg-warning text-black q-mb-sm" role="alert" data-testid="player-server-running">
        <div>{{ t('playerFiles.edit.serverRunning') }}</div>
        <q-checkbox v-model="confirmServer" :label="t('playerFiles.edit.confirmServer')" data-testid="confirm-server" />
      </q-banner>

      <div v-if="detail && !detail.problem" class="q-mb-sm text-body2" data-testid="player-summary">
        <span v-if="detail.level !== null">{{ t('playerFiles.detail.level', { n: detail.level }) }}</span>
        <span v-if="detail.classLabel"> · {{ detail.classLabel }}</span>
        <span v-if="detail.raceLabel"> · {{ detail.raceLabel }}</span>
        <span v-if="detail.sex"> · {{ sexLabel(detail.sex) }}</span>
        <span> · {{ detail.hasPassword ? t('playerFiles.detail.passwordSet') : t('playerFiles.detail.passwordNone') }}</span>
      </div>

      <q-tabs v-model="tab" dense align="left" class="text-primary" active-color="primary" indicator-color="primary">
        <q-tab name="details" :label="t('playerFiles.detail.tabs.details')" />
        <q-tab v-if="lists.length" name="lists" :label="t('playerFiles.detail.tabs.lists')" />
        <q-tab v-if="inventoryEnabled || liveInventory" name="inventory" :label="t('playerFiles.detail.tabs.inventory')" data-testid="tab-inventory" />
      </q-tabs>
      <q-separator />
      <q-tab-panels v-model="tab" animated>
        <q-tab-panel name="details" class="q-px-none" data-testid="panel-details">
          <div v-for="section in sections" :key="section.group" class="q-mb-md">
            <div class="text-subtitle2 q-mb-xs" :data-testid="`section-${section.group}`">{{ groupLabel(section.group) }}</div>
            <q-markup-table dense flat bordered>
              <tbody>
                <tr v-for="field in section.fields" :key="field.name">
                  <th class="text-left" style="width: 35%">{{ labelOf(field.labelKey, field.name) }}</th>
                  <td :data-testid="`field-${field.name}`">
                    <player-field-editor
                      v-if="editing && !field.readOnly"
                      v-model="draft[field.name]"
                      :field="field"
                      :enums="enums"
                      :label="labelOf(field.labelKey, field.name)"
                    />
                    <template v-else-if="field.type === 'flags'">
                      <q-chip v-for="flag in asList(detail?.details[field.name])" :key="flag" dense>{{ flag }}</q-chip>
                      <span v-if="asList(detail?.details[field.name]).length === 0">—</span>
                    </template>
                    <pre v-else-if="field.type === 'json'" class="q-ma-none">{{ prettyJson(detail?.details[field.name]) }}</pre>
                    <span v-else class="text-pre-wrap">{{ cell(detail?.details[field.name], field.type, field) }}</span>
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
          </div>
        </q-tab-panel>

        <q-tab-panel v-if="lists.length" name="lists" class="q-px-none" data-testid="panel-lists">
          <div v-for="list in lists" :key="list.name" class="q-mb-md">
            <div class="text-subtitle2 q-mb-xs">{{ labelOf(list.labelKey, list.name) }}</div>
            <json-field
              v-if="editing"
              v-model="draftLists[list.name]"
              :label="labelOf(list.labelKey, list.name)"
              :hint="t('playerFiles.edit.listHint')"
              :data-testid="`edit-list-${list.name}`"
            />
            <pachi-table2
              v-else
              :rows="listRows(list.name)"
              :columns="listColumns(list)"
              row-key="__row"
              dense
              single-sort
              :initial-sort="[]"
              :auto-height="false"
              :no-data-label="t('playerFiles.empty')"
              :data-testid="`list-${list.name}`"
            />
          </div>
        </q-tab-panel>

        <q-tab-panel v-if="inventoryEnabled || liveInventory" name="inventory" class="q-px-none">
          <live-inventory-panel
            v-if="liveInventory"
            :player-name="playerName"
            :can-edit="live.canWriteInventory.value"
            :can-write="live.canWriteInventory.value"
            @unavailable="liveInventoryFailed = true"
          />
          <player-inventory-panel
            v-else
            :player-id="playerId"
            :can-write="canWriteInventory"
            :wear-slots="info?.wearSlots ?? []"
            :blocked="serverBlocked"
            :confirm-server-running="confirmServer"
          />
        </q-tab-panel>
      </q-tab-panels>
    </div>
    <template #actions>
      <template v-if="editing">
        <q-btn flat :label="t('playerFiles.cancel')" data-testid="edit-cancel" @click="editing = false" />
        <q-btn
          color="primary"
          :label="t('playerFiles.edit.save')"
          :disable="saving || serverBlocked"
          :loading="saving"
          data-testid="edit-save"
          @click="save"
        />
      </template>
      <template v-else>
        <q-btn
          v-if="liveEditable"
          outline
          color="negative"
          :icon="mdiLightningBolt"
          :label="t('playerFiles.live.detail.editLive')"
          data-testid="live-edit-start"
          @click="startLiveEdit"
        />
        <q-btn
          v-if="canWrite && detail && !detail.problem && !liveEditable"
          outline
          color="primary"
          :icon="mdiPencil"
          :label="t('playerFiles.edit.start')"
          data-testid="edit-start"
          @click="startEdit"
        />
        <q-btn flat :label="t('playerFiles.close')" @click="onDialogCancel" />
      </template>
    </template>
  </pachi-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialogPluginComponent, useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import { mdiLightningBolt, mdiPencil } from '@quasar/extras/mdi-v7'
import { PachiDialog } from '@ilpachi/pachi-kit/dialog'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import { describeError } from '../../players/helpers/describe-error'
import JsonField from '../../shared/components/JsonField.vue'
import { useWorld } from '../../shared/helpers/world-state'
import { errorCode } from '../helpers/error-code'
import { formatCell } from '../helpers/format'
import { getPlayer, getPlayerEnums, getPlayersInfo, getPlayersStatus, updatePlayer } from '../services/player-files-api'
import type { IPlayerDetail, IPlayerListInfo, IPlayersInfo, IPlayersStatus } from '../types/player-files'
import type { IExtraFieldDescriptor } from '../../shared/types/worlds'
import PlayerFieldEditor from './PlayerFieldEditor.vue'
import PlayerInventoryPanel from './PlayerInventoryPanel.vue'
import LiveInventoryPanel from './LiveInventoryPanel.vue'
import LivePlayerDialog from './LivePlayerDialog.vue'
import { useLive } from '../helpers/live-state'

const props = defineProps<{
  /** Id opaco del giocatore. */
  playerId: string
  /** Nome (titolo). */
  playerName: string
}>()

defineEmits([...useDialogPluginComponent.emits])

const { t, te, locale } = useI18n()
const $q = useQuasar()
const { dialogRef, onDialogHide, onDialogCancel } = useDialogPluginComponent()
const { capabilities } = useWorld()
const live = useLive()

const tab = ref<'details' | 'lists' | 'inventory'>('details')
const info = ref<IPlayersInfo>()
const detail = ref<IPlayerDetail>()
const status = ref<IPlayersStatus>()
const enums = ref<Record<string, unknown>>()
const error = ref('')
const editing = ref(false)
const saving = ref(false)
const confirmServer = ref(false)
const draft = ref<Record<string, unknown>>({})
const draftLists = ref<Record<string, unknown>>({})

/** Il canale non ha risposto al caricamento dell'inventario live: si ripiega sul file. */
const liveInventoryFailed = ref(false)
const inventoryEnabled = computed(() => capabilities.value?.supportsPlayerInventory === true)
const lists = computed<IPlayerListInfo[]>(() => info.value?.detailLists ?? [])
const readOnlyWorld = computed(() => capabilities.value?.readOnly === true)
/** Il mondo permette di modificare i campi del giocatore. */
const canWrite = computed(() => capabilities.value?.supportsPlayerWrite === true && !readOnlyWorld.value)
/** Il mondo permette di modificare l'inventario. */
const canWriteInventory = computed(() => capabilities.value?.supportsPlayerInventoryWrite === true && !readOnlyWorld.value)
/** Server acceso e conferma non data: nessuna scrittura. */
const serverBlocked = computed(() => status.value?.serverRunning === true && !confirmServer.value)

/** Il giocatore e' in gioco e il canale permette di scrivere: la modifica passa dal canale (subito nel gioco) invece che dal file. */
const liveEditable = computed(() => live.canWrite.value && detail.value?.online === true && detail.value.extra.liveState === 'playing')

/** Inventario LIVE: giocatore in gioco, canale con la feature `inventory` e utente superuser (altrimenti il file, come prima). */
const liveInventory = computed(
  () => live.inventory.value && !liveInventoryFailed.value && detail.value?.online === true && detail.value.extra.liveState === 'playing',
)

/** Campi del dettaglio raggruppati per sezione, nell'ordine dichiarato dall'adapter. */
const sections = computed(() => {
  const groups = new Map<string, IExtraFieldDescriptor[]>()
  for (const field of info.value?.detailFields ?? []) {
    const group = field.group ?? 'general'
    groups.set(group, [...(groups.get(group) ?? []), field])
  }
  return [...groups].map(([group, fields]) => ({ group, fields }))
})

/** Etichetta tradotta di una chiave dichiarata dall'adapter (ripiega sul nome). */
function labelOf(key: string, fallback: string): string {
  return te(key) ? t(key) : fallback
}

/** Titolo di sezione (`playerFiles.group.<gruppo>`). */
function groupLabel(group: string): string {
  return labelOf(`playerFiles.group.${group}`, group)
}

/** Testo di un codice di problema del file. */
function problemLabel(code: string): string {
  return labelOf(`playerFiles.problems.${code}`, code)
}

/** Sesso come testo (`neutral|male|female` tradotti, altro invariato). */
function sexLabel(code: string): string {
  return labelOf(`playerFiles.sex.${code}`, code)
}

/** Un valore come lista di stringhe (per i campi `flags`). */
function asList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : []
}

/** JSON leggibile di un valore strutturato. */
function prettyJson(value: unknown): string {
  return value === null || value === undefined ? '—' : JSON.stringify(value, null, 1)
}

/**
 * Valore semplice formattato per il tipo del campo (`number`/`boolean`/`text`); gli `enum` mostrano l'etichetta dell'opzione.
 *
 * @param value - valore grezzo
 * @param type - tipo dichiarato
 * @param field - descrittore (per l'enum)
 */
function cell(value: unknown, type: string, field?: IExtraFieldDescriptor): string {
  if (type === 'enum' && field?.enum) {
    const options = enums.value?.[field.enum]
    const hit = Array.isArray(options) ? (options as { value: unknown; label: string }[]).find((o) => o.value === value) : undefined
    if (hit) return hit.label
  }
  const kind = type === 'number' ? 'number' : type === 'boolean' ? 'boolean' : 'text'
  return formatCell(value, kind, locale.value, t('playerFiles.yes'), t('playerFiles.no'))
}

/** Righe di una tabella del dettaglio con una chiave di riga stabile (indice). */
function listRows(name: string): Record<string, unknown>[] {
  return (detail.value?.lists[name] ?? []).map((row, index) => ({ ...row, __row: index }))
}

/** Colonne di una tabella del dettaglio. */
function listColumns(list: IPlayerListInfo): QTableColumn[] {
  return list.columns.map((c) => ({
    name: c.name,
    label: labelOf(c.labelKey, c.name),
    field: c.name,
    align: 'right' as const,
    format: (v: unknown) => formatCell(v, c.type, locale.value, t('playerFiles.yes'), t('playerFiles.no')),
  }))
}

/** Apre la modifica live; alla chiusura rilegge il dettaglio (i valori del file possono essere cambiati dal salvataggio del gioco). */
function startLiveEdit(): void {
  $q.dialog({ component: LivePlayerDialog, componentProps: { playerName: props.playerName } }).onDismiss(() => {
    void getPlayer(props.playerId).then((d) => (detail.value = d))
  })
}

/** Entra in modifica con una copia dei valori correnti. */
function startEdit(): void {
  draft.value = structuredClone(JSON.parse(JSON.stringify(detail.value?.details ?? {})) as Record<string, unknown>)
  draftLists.value = structuredClone(JSON.parse(JSON.stringify(detail.value?.lists ?? {})) as Record<string, unknown>)
  error.value = ''
  editing.value = true
}

/** I soli campi/tabelle cambiati rispetto al dettaglio letto. */
function changes(): { details: Record<string, unknown>; lists: Record<string, unknown> } {
  const same = (a: unknown, b: unknown): boolean => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
  const details: Record<string, unknown> = {}
  for (const field of info.value?.detailFields ?? []) {
    if (field.readOnly) continue
    if (!same(draft.value[field.name], detail.value?.details[field.name])) details[field.name] = draft.value[field.name]
  }
  const changed: Record<string, unknown> = {}
  for (const list of lists.value) {
    if (draftLists.value[list.name] !== undefined && !same(draftLists.value[list.name], detail.value?.lists[list.name]))
      changed[list.name] = draftLists.value[list.name]
  }
  return { details, lists: changed }
}

/** Salva le modifiche; in caso di errore resta in modifica con il messaggio. */
async function save(): Promise<void> {
  const { details, lists: changedLists } = changes()
  if (Object.keys(details).length === 0 && Object.keys(changedLists).length === 0) {
    editing.value = false
    return
  }
  saving.value = true
  error.value = ''
  try {
    detail.value = await updatePlayer(props.playerId, {
      revision: detail.value?.revision ?? null,
      details,
      lists: changedLists as Record<string, Record<string, unknown>[]>,
      confirmServerRunning: confirmServer.value,
    })
    editing.value = false
    $q.notify({ type: 'positive', message: t('playerFiles.edit.saved') })
  } catch (e) {
    const code = await errorCode(e)
    error.value = await describeError(e)
    if (code === 'worldplayers.server_running') status.value = { serverRunning: true, detection: status.value?.detection ?? 'proc' }
    if (code === 'worldplayers.conflict') editing.value = false
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    info.value = await getPlayersInfo()
    detail.value = await getPlayer(props.playerId)
  } catch (e) {
    error.value = await describeError(e)
    return
  }
  getPlayersStatus()
    .then((s) => (status.value = s))
    .catch(() => undefined) // stato non rilevabile: nessuna conferma richiesta
  getPlayerEnums()
    .then((e) => (enums.value = e))
    .catch(() => undefined) // senza enum i campi enum/flags restano visibili ma senza opzioni
})
</script>
