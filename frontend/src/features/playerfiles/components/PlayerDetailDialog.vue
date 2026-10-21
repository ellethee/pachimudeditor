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
      <q-banner rounded class="bg-grey-3 text-black q-mb-sm" role="note" data-testid="player-readonly-note">
        {{ t('playerFiles.detail.readOnly') }}
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
        <q-tab v-if="inventoryEnabled" name="inventory" :label="t('playerFiles.detail.tabs.inventory')" data-testid="tab-inventory" />
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
                    <template v-if="field.type === 'flags'">
                      <q-chip v-for="flag in asList(detail?.details[field.name])" :key="flag" dense>{{ flag }}</q-chip>
                      <span v-if="asList(detail?.details[field.name]).length === 0">—</span>
                    </template>
                    <pre v-else-if="field.type === 'json'" class="q-ma-none">{{ prettyJson(detail?.details[field.name]) }}</pre>
                    <span v-else class="text-pre-wrap">{{ cell(detail?.details[field.name], field.type) }}</span>
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
          </div>
        </q-tab-panel>

        <q-tab-panel v-if="lists.length" name="lists" class="q-px-none" data-testid="panel-lists">
          <div v-for="list in lists" :key="list.name" class="q-mb-md">
            <div class="text-subtitle2 q-mb-xs">{{ labelOf(list.labelKey, list.name) }}</div>
            <q-table
              :rows="listRows(list.name)"
              :columns="listColumns(list)"
              row-key="__row"
              dense
              flat
              bordered
              :rows-per-page-options="[0]"
              hide-pagination
              :no-data-label="t('playerFiles.empty')"
              :data-testid="`list-${list.name}`"
            />
          </div>
        </q-tab-panel>

        <q-tab-panel v-if="inventoryEnabled" name="inventory" class="q-px-none" data-testid="panel-inventory">
          <q-banner v-if="inventory?.problem" rounded class="bg-warning text-black q-mb-sm" data-testid="inventory-problem">
            {{ problemLabel(inventory.problem) }}
          </q-banner>
          <div v-if="rentInfo" class="text-caption q-mb-sm" data-testid="inventory-rent">{{ rentInfo }}</div>
          <q-table
            :rows="inventory?.items ?? []"
            :columns="inventoryColumns"
            row-key="id"
            dense
            flat
            bordered
            :loading="inventoryLoading"
            :rows-per-page-options="[0]"
            hide-pagination
            :no-data-label="t('playerFiles.inventory.empty')"
            data-testid="inventory-table"
          >
            <template #body-cell-name="{ row }">
              <q-td>
                <span :style="{ paddingLeft: `${row.depth * 16}px` }">{{ row.name || '—' }}</span>
                <q-chip v-if="!row.known" dense color="grey-6" text-color="white" class="q-ml-sm">
                  {{ t('playerFiles.inventory.unknown') }}
                </q-chip>
              </q-td>
            </template>
          </q-table>
        </q-tab-panel>
      </q-tab-panels>
    </div>
    <template #actions>
      <q-btn flat :label="t('playerFiles.close')" @click="onDialogCancel" />
    </template>
  </pachi-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialogPluginComponent } from 'quasar'
import type { QTableColumn } from 'quasar'
import { PachiDialog } from '@ilpachi/pachi-kit/dialog'
import { describeError } from '../../players/helpers/describe-error'
import { useWorld } from '../../shared/helpers/world-state'
import { formatCell } from '../helpers/format'
import { getPlayer, getPlayerInventory, getPlayersInfo } from '../services/player-files-api'
import type { IPlayerDetail, IPlayerInventory, IPlayerListInfo, IPlayersInfo } from '../types/player-files'
import type { IExtraFieldDescriptor } from '../../shared/types/worlds'

const props = defineProps<{
  /** Id opaco del giocatore. */
  playerId: string
  /** Nome (titolo). */
  playerName: string
}>()

defineEmits([...useDialogPluginComponent.emits])

const { t, te, locale } = useI18n()
const { dialogRef, onDialogHide, onDialogCancel } = useDialogPluginComponent()
const { capabilities } = useWorld()

const tab = ref<'details' | 'lists' | 'inventory'>('details')
const info = ref<IPlayersInfo>()
const detail = ref<IPlayerDetail>()
const inventory = ref<IPlayerInventory>()
const inventoryLoading = ref(false)
const error = ref('')

const inventoryEnabled = computed(() => capabilities.value?.supportsPlayerInventory === true)
const lists = computed<IPlayerListInfo[]>(() => info.value?.detailLists ?? [])

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

/** Valore semplice formattato per il tipo del campo (`number`/`boolean`/`text`). */
function cell(value: unknown, type: string): string {
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

const inventoryColumns = computed<QTableColumn[]>(() => [
  { name: 'vnum', label: t('playerFiles.inventory.vnum'), field: 'vnum', align: 'left' },
  { name: 'name', label: t('playerFiles.inventory.name'), field: 'name', align: 'left' },
  {
    name: 'where',
    label: t('playerFiles.inventory.where'),
    field: (row: { wearSlot: string | null; depth: number }) =>
      row.wearSlot ? labelOf(`playerFiles.slots.${row.wearSlot}`, row.wearSlot) : row.depth > 0 ? t('playerFiles.inventory.inContainer') : t('playerFiles.inventory.carried'),
    align: 'left',
  },
])

/** Riga con testata del rent («oro lasciato», «costo giornaliero»), se il file esiste. */
const rentInfo = computed(() => {
  const extra = inventory.value?.extra
  if (!extra || extra.rentFile !== true) return ''
  return t('playerFiles.inventory.rent', { gold: extra.goldLeft ?? 0, cost: extra.totalCost ?? 0, n: extra.declaredNumber ?? 0 })
})

onMounted(async () => {
  try {
    info.value = await getPlayersInfo()
    detail.value = await getPlayer(props.playerId)
  } catch (e) {
    error.value = await describeError(e)
    return
  }
  if (inventoryEnabled.value) {
    inventoryLoading.value = true
    try {
      inventory.value = await getPlayerInventory(props.playerId)
    } catch (e) {
      error.value = await describeError(e)
    } finally {
      inventoryLoading.value = false
    }
  }
})
</script>
