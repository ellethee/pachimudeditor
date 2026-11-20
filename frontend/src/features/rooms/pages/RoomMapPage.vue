<template>
  <div class="column no-wrap q-px-md q-pt-md" style="height: var(--pachi-page-height, 70vh)">
    <div class="row items-center q-gutter-sm q-pb-sm" style="flex: 0 0 auto">
      <h1 class="text-h5 q-ma-none">{{ t('rooms.map.title') }}</h1>
      <q-select
        v-model="store.selectedZoneId"
        :options="zoneOptions"
        option-value="id"
        option-label="label"
        emit-value
        map-options
        :label="t('rooms.zone')"
        style="min-width: 240px"
        dense
        outlined
      />
      <q-select
        v-model="searchRoom"
        :options="searchOptions"
        option-value="id"
        option-label="label"
        emit-value
        map-options
        use-input
        clearable
        dense
        outlined
        input-debounce="0"
        :label="t('rooms.map.search')"
        style="min-width: 220px"
        data-testid="map-search"
        @filter="onSearchFilter"
        @update:model-value="onSearchPick"
      />
      <q-btn flat dense :icon="mdiFitToScreen" :label="t('rooms.map.fit')" @click="fitAll" />
      <q-btn flat dense :icon="mdiRefresh" :label="t('rooms.map.reload')" :loading="loading" @click="load" />
      <q-btn flat dense :icon="mdiRestore" :label="t('rooms.map.resetLayout')" :disable="store.selectedZoneId === null" data-testid="map-reset-layout" @click="resetLayout">
        <q-tooltip>{{ t('rooms.map.resetLayoutHint') }}</q-tooltip>
      </q-btn>
      <q-btn flat dense :icon="mdiPlus" :label="t('rooms.map.newRoom')" :disable="!selectedRoom || readOnly" data-testid="map-new-room" @click="newRoomDialog = true">
        <q-tooltip>{{ t('rooms.map.newRoomHint') }}</q-tooltip>
      </q-btn>
      <q-btn flat dense :icon="mdiFormatListBulleted" :label="t('rooms.map.openList')" to="/rooms" />
      <q-space />
      <q-btn flat dense :icon="mdiHelpCircleOutline" :label="t('rooms.map.legend')" @click="showLegend = !showLegend" />
    </div>

    <div class="relative-position" style="flex: 1 1 auto; min-height: 0">
      <VueFlow
        v-if="!loading"
        :nodes="nodes"
        :edges="edges"
        :min-zoom="0.1"
        :max-zoom="2"
        :connection-radius="45"
        :default-viewport="{ zoom: 0.8 }"
        @nodes-initialized="fitAll"
        @connect="onConnect"
        @node-click="onNodeClick"
        @node-double-click="onNodeDoubleClick"
        @node-drag-stop="onNodeDragStop"
        @edge-click="onEdgeClick"
        @pane-click="clearSelection"
      >
        <template #node-room="nodeProps">
          <room-node v-bind="nodeProps" />
        </template>
        <Background :gap="24" pattern-color="#b0bec5" />
        <Controls position="bottom-left" />
        <MiniMap pannable zoomable :node-color="miniMapColor" />
      </VueFlow>

      <div v-if="!loading && store.selectedZoneId !== null && nodes.length === 0" class="absolute-center text-grey-7">
        {{ t('rooms.map.empty') }}
      </div>
      <div v-else-if="!selectedRoom && !selectedEdge" class="absolute-top-right q-pa-sm text-caption text-grey">
        {{ t('rooms.map.hint') }}
      </div>

      <q-card v-if="showLegend" class="room-map__legend" flat bordered data-testid="map-legend">
        <q-card-section class="q-pa-sm">
          <div class="text-subtitle2">{{ t('rooms.map.legendSectors') }}</div>
          <div v-for="option in store.enums?.sectorType ?? []" :key="option.value" class="row items-center no-wrap">
            <span class="room-map__swatch" :style="{ background: sectorColor(option.value) }"></span>
            <span class="text-caption">{{ option.label }}</span>
          </div>
          <div class="text-subtitle2 q-mt-sm">{{ t('rooms.map.legendLinks') }}</div>
          <div class="text-caption" style="white-space: pre-line">{{ t('rooms.map.legendLinksText') }}</div>
        </q-card-section>
      </q-card>

      <q-card v-if="selectedEdge" class="room-map__panel" flat bordered data-testid="map-edge-panel">
        <q-card-section class="q-pb-none">
          <div class="text-subtitle1">{{ t('rooms.map.exit', { direction: shortLabel(selectedEdge.direction as DirectionValue) }) }}</div>
          <div class="text-caption">
            {{ nodeLabel(selectedEdge.fromRoomId) }} {{ selectedEdge.twoWay ? '⇄' : '→' }} {{ nodeLabel(selectedEdge.toRoomId) }}
          </div>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-select v-model="doorEdit.doorFlag" :options="store.enums?.doorFlag ?? []" emit-value map-options outlined dense :label="t('rooms.exits.door')" :disable="readOnly" />
          <div class="row">
            <q-toggle v-model="doorEdit.isOpen" :label="t('rooms.exits.open')" :disable="readOnly" />
            <q-toggle v-model="doorEdit.isLocked" :label="t('rooms.exits.locked')" :disable="readOnly" />
          </div>
          <q-input v-model="doorEdit.keywords" outlined dense :label="t('rooms.exits.keywords')" :disable="readOnly" />
          <q-btn v-if="!readOnly" color="primary" dense no-caps :label="t('rooms.map.saveDoor')" :loading="busy" data-testid="map-save-door" @click="saveDoor" />
        </q-card-section>
        <template v-if="!readOnly">
          <q-separator />
          <q-card-actions vertical>
            <q-btn flat color="negative" no-caps :icon="mdiLinkOff" :label="t('rooms.map.removeExit')" :disable="busy" data-testid="map-remove-exit" @click="askRemoveExit(false)" />
            <q-btn v-if="selectedEdge.twoWay" flat color="negative" no-caps :icon="mdiLinkOff" :label="t('rooms.map.removeBoth')" :disable="busy" @click="askRemoveExit(true)" />
          </q-card-actions>
        </template>
      </q-card>

      <q-card v-else-if="selectedRoom" class="room-map__panel" flat bordered data-testid="map-room-panel">
        <q-card-section class="q-pb-none">
          <div class="text-subtitle1">#{{ selectedRoom.vnum }} — {{ selectedRoom.name }}</div>
          <div v-if="selectedRoom.flags.length > 0" class="text-caption">{{ selectedRoom.flags.join(', ') }}</div>
          <div v-if="selectedRoom.danglingExits > 0" class="text-caption text-orange-9">
            {{ t('rooms.map.dangling', { count: selectedRoom.danglingExits }) }}
          </div>
        </q-card-section>
        <q-card-actions vertical>
          <q-btn flat no-caps color="primary" :icon="mdiOpenInNew" :label="t('rooms.map.openRoom')" data-testid="map-open-room" @click="openRoom(selectedRoom.id)" />
          <q-btn v-if="!readOnly" flat no-caps color="primary" :icon="mdiSignDirection" :label="t('rooms.map.newLinkedRoom')" @click="newRoomDialog = true" />
          <q-btn flat no-caps color="primary" :icon="mdiCrosshairsGps" :label="t('rooms.map.center')" @click="focusRoom(selectedRoom.id)" />
        </q-card-actions>
      </q-card>
    </div>

    <room-link-dialog
      v-if="pendingLink"
      v-model="linkDialog"
      :from-room-id="pendingLink.fromRoomId"
      :to-room-id="pendingLink.toRoomId"
      :from-label="nodeLabel(pendingLink.fromRoomId)"
      :to-label="nodeLabel(pendingLink.toRoomId)"
      :initial-direction="pendingLink.direction"
      :taken-from="takenDirectionsOf(pendingLink.fromRoomId)"
      :taken-to="takenDirectionsOf(pendingLink.toRoomId)"
      @linked="onLinked"
    />
    <new-linked-room-dialog
      v-if="selectedRoom && store.selectedZoneId !== null"
      v-model="newRoomDialog"
      :from-room-id="selectedRoom.id"
      :from-label="`#${selectedRoom.vnum}`"
      :zone-id="store.selectedZoneId"
      :taken-directions="takenDirectionsOf(selectedRoom.id)"
      @created="onRoomCreated"
    />
  </div>
</template>

<script setup lang="ts">
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import { computed, nextTick, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import {
  mdiCrosshairsGps,
  mdiFitToScreen,
  mdiFormatListBulleted,
  mdiHelpCircleOutline,
  mdiLinkOff,
  mdiOpenInNew,
  mdiPlus,
  mdiRefresh,
  mdiRestore,
  mdiSignDirection,
} from '@quasar/extras/mdi-v7'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import type { Connection, Edge, EdgeMouseEvent, Node, NodeDragEvent, NodeMouseEvent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { useFlowControlLabels } from '../../shared/helpers/flow-controls'
import { useWorld } from '../../shared/helpers/world-state'
import NewLinkedRoomDialog from '../components/NewLinkedRoomDialog.vue'
import RoomLinkDialog from '../components/RoomLinkDialog.vue'
import RoomNode from '../components/RoomNode.vue'
import { getRoom, getRoomGraph, removeExit, updateExit } from '../services/rooms-api'
import { useRoomsStore } from '../stores/use-rooms-store'
import type { IGraphEdge, IGraphNode, IRoomGraph } from '../types/rooms'
import { OPPOSITE } from '../utils/compass'
import type { DirectionValue } from '../utils/compass'
import { describeError } from '../utils/error-helper'
import { directionOfHandle, exitIdOf, graphToFlow, nodeId } from '../utils/graph-mapper'
import type { RoomEdgeData, RoomNodeData } from '../utils/graph-mapper'
import { clearLayout, loadLayout, saveLayout } from '../utils/layout-storage'
import type { LayoutOverrides } from '../utils/layout-storage'
import { sectorColor } from '../utils/sector-style'

/**
 * Editor visuale della mappa delle stanze di una zona (grafo vue-flow, layout calcolato dal server). Trascinando da
 * una maniglia all'altra si crea un collegamento (dialogo piccolo: direzione, porta, ritorno); un clic su un arco apre
 * il pannello della porta (modifica/eliminazione dell'uscita), un clic su una stanza quello della stanza (apri scheda,
 * nuova stanza collegata, centra). Le posizioni trascinate a mano restano in localStorage per zona.
 */
const { t, te } = useI18n()
const $q = useQuasar()
const router = useRouter()
const route = useRoute()
const store = useRoomsStore()
const { readOnly } = useWorld()
const { fitView } = useVueFlow()

const graph = ref<IRoomGraph>({ nodes: [], edges: [] })
const nodes = shallowRef<Node<RoomNodeData>[]>([])
useFlowControlLabels(nodes)
const edges = shallowRef<Edge<RoomEdgeData>[]>([])
const loading = ref(false)
const busy = ref(false)
const showLegend = ref(false)
let loadSeq = 0
let overrides: LayoutOverrides = {}

const selectedRoomId = ref<number | null>(null)
const selectedEdgeId = ref<number | null>(null)
const highlightedId = ref<number | null>(null)
const pendingFocusId = ref<number | null>(null)

const selectedRoom = computed<IGraphNode | null>(() => graph.value.nodes.find((node) => node.id === selectedRoomId.value) ?? null)
const selectedEdge = computed<IGraphEdge | null>(() => graph.value.edges.find((edge) => edge.id === selectedEdgeId.value) ?? null)
const doorEdit = reactive({ doorFlag: 0, isOpen: true, isLocked: false, keywords: '' })

const zoneOptions = computed(() => store.zones.map((zone) => ({ id: zone.id, label: `${zone.vnum} - ${zone.name}` })))

/** Etichetta breve (N, E, S, O, Su, Giù) di una direzione. */
function shortLabel(direction: DirectionValue): string {
  return t(`rooms.map.dir.${direction}`)
}

/** Etichetta `#vnum nome` di una stanza del grafo. */
function nodeLabel(roomId: number): string {
  const room = graph.value.nodes.find((node) => node.id === roomId)
  return room ? `#${room.vnum} ${room.name}` : `#${roomId}`
}

/** Direzioni già usate dalle uscite note di una stanza (quelle senza destinazione non compaiono nel grafo: il server le rifiuta). */
function takenDirectionsOf(roomId: number): DirectionValue[] {
  const taken: DirectionValue[] = []
  for (const edge of graph.value.edges) {
    if (edge.fromRoomId === roomId) taken.push(edge.direction as DirectionValue)
    else if (edge.toRoomId === roomId && edge.twoWay) taken.push(OPPOSITE[edge.direction as DirectionValue])
  }
  return taken
}

/** Ricostruisce nodi e archi vue-flow dal grafo, dalle posizioni salvate e dall'evidenziazione. */
function rebuild(): void {
  const flow = graphToFlow(graph.value.nodes, graph.value.edges, shortLabel, overrides, highlightedId.value)
  nodes.value = flow.nodes
  edges.value = flow.edges
}

/** Carica il grafo della zona selezionata. */
async function load(): Promise<void> {
  if (store.selectedZoneId === null) {
    graph.value = { nodes: [], edges: [] }
    rebuild()
    return
  }
  // caricamenti sovrapposti (zona di default, poi zona del deep-link): vale solo l'ultimo
  const ticket = ++loadSeq
  loading.value = true
  try {
    const loaded = await getRoomGraph(store.selectedZoneId)
    if (ticket !== loadSeq) return
    graph.value = loaded
    overrides = loadLayout(store.selectedZoneId)
    if (selectedRoomId.value !== null && !selectedRoom.value) selectedRoomId.value = null
    if (selectedEdgeId.value !== null && !selectedEdge.value) selectedEdgeId.value = null
    rebuild()
  } finally {
    if (ticket === loadSeq) loading.value = false
  }
  await nextTick()
  if (pendingFocusId.value !== null) {
    focusRoom(pendingFocusId.value)
    pendingFocusId.value = null
  } else fitAll()
}

/** Adatta la vista a tutto il grafo. */
function fitAll(): void {
  void fitView({ padding: 0.2 })
}

/** Evidenzia e centra una stanza. */
function focusRoom(roomId: number): void {
  highlightedId.value = roomId
  rebuild()
  void nextTick(() => fitView({ nodes: [nodeId(roomId)], padding: 1.5, maxZoom: 1.1, duration: 400 }))
}

/** Dimentica le posizioni trascinate a mano. */
function resetLayout(): void {
  if (store.selectedZoneId === null) return
  clearLayout(store.selectedZoneId)
  overrides = {}
  rebuild()
  void nextTick(fitAll)
}

/** Colore di un nodo nella minimappa. */
function miniMapColor(node: Node): string {
  const room = (node.data as RoomNodeData | undefined)?.room
  return room ? sectorColor(room.sectorType) : '#90a4ae'
}

// ---- selezione -------------------------------------------------------------------------------

function clearSelection(): void {
  selectedRoomId.value = null
  selectedEdgeId.value = null
}

/** Clic su un nodo: pannello della stanza. */
function onNodeClick({ node }: NodeMouseEvent): void {
  selectedEdgeId.value = null
  selectedRoomId.value = Number(node.id)
}

/** Doppio clic: apre la scheda della stanza. */
function onNodeDoubleClick({ node }: NodeMouseEvent): void {
  openRoom(Number(node.id))
}

/** Apre la pagina di dettaglio della stanza. */
function openRoom(roomId: number): void {
  void router.push(`/rooms/${roomId}`)
}

/** Clic su un arco: pannello della porta, con i valori correnti letti dall'uscita. */
async function onEdgeClick({ edge }: EdgeMouseEvent): Promise<void> {
  const exitId = exitIdOf(edge)
  if (exitId === null) return
  selectedRoomId.value = null
  selectedEdgeId.value = exitId
  const found = graph.value.edges.find((candidate) => candidate.id === exitId)
  if (!found) return
  Object.assign(doorEdit, { doorFlag: found.doorFlag, isOpen: true, isLocked: false, keywords: '' })
  try {
    const exit = (await getRoom(found.fromRoomId)).exits.find((candidate) => candidate.id === exitId)
    if (exit && selectedEdgeId.value === exitId) {
      Object.assign(doorEdit, { doorFlag: exit.doorFlag, isOpen: exit.isOpen, isLocked: exit.isLocked, keywords: exit.keywords ?? '' })
    }
  } catch {
    // restano i valori del grafo
  }
}

/** Fine del trascinamento di un nodo: la posizione si ricorda per zona. */
function onNodeDragStop({ node }: NodeDragEvent): void {
  if (store.selectedZoneId === null) return
  overrides[node.id] = { x: Math.round(node.position.x), y: Math.round(node.position.y) }
  saveLayout(store.selectedZoneId, overrides)
}

// ---- collegamenti ----------------------------------------------------------------------------

const linkDialog = ref(false)
const pendingLink = ref<{ fromRoomId: number; toRoomId: number; direction: DirectionValue } | null>(null)

/** Fine di un trascinamento tra due maniglie: apre il dialogo di collegamento. */
function onConnect(connection: Connection): void {
  if (readOnly.value) return
  if (connection.source === connection.target) {
    $q.notify({ type: 'warning', message: t('rooms.map.selfLink') })
    return
  }
  pendingLink.value = {
    fromRoomId: Number(connection.source),
    toRoomId: Number(connection.target),
    direction: directionOfHandle(connection.sourceHandle) ?? 0,
  }
  linkDialog.value = true
}

/** Collegamento creato. */
function onLinked(): void {
  $q.notify({ type: 'positive', message: t('rooms.map.linked') })
  void load()
}

/** Salva porta e parole chiave sull'uscita (e sul ritorno, se a due sensi). */
async function saveDoor(): Promise<void> {
  const edge = selectedEdge.value
  if (!edge) return
  const none = doorEdit.doorFlag === (store.enums?.doorFlag[0]?.value ?? 0)
  const payload = {
    doorFlag: doorEdit.doorFlag,
    isOpen: none ? true : doorEdit.isOpen,
    isLocked: none ? false : doorEdit.isLocked,
    keywords: doorEdit.keywords.trim() || null,
  }
  busy.value = true
  try {
    const silent = { autoError: false }
    await updateExit(edge.fromRoomId, edge.id, payload, silent)
    if (edge.twoWay && edge.reverseExitId !== null) await updateExit(edge.toRoomId, edge.reverseExitId, payload, silent)
    $q.notify({ type: 'positive', message: t('rooms.map.doorSaved') })
    await load()
  } catch (error) {
    $q.notify({ type: 'negative', message: await describeError(error, t, te) })
  } finally {
    busy.value = false
  }
}

/**
 * Elimina l'uscita selezionata dopo conferma.
 *
 * @param bothWays - elimina anche l'uscita di ritorno
 */
function askRemoveExit(bothWays: boolean): void {
  const edge = selectedEdge.value
  if (!edge) return
  $q.dialog({
    title: t('rooms.map.removeTitle'),
    message: t(bothWays ? 'rooms.map.removeBothConfirm' : 'rooms.map.removeConfirm', {
      from: nodeLabel(edge.fromRoomId),
      to: nodeLabel(edge.toRoomId),
    }),
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    busy.value = true
    try {
      const silent = { autoError: false }
      await removeExit(edge.fromRoomId, edge.id, silent)
      if (bothWays && edge.reverseExitId !== null) await removeExit(edge.toRoomId, edge.reverseExitId, silent)
      selectedEdgeId.value = null
      await load()
    } catch (error) {
      $q.notify({ type: 'negative', message: await describeError(error, t, te) })
    } finally {
      busy.value = false
    }
  })
}

// ---- stanze ----------------------------------------------------------------------------------

const newRoomDialog = ref(false)

/** Stanza creata: ricarica e la centra. */
function onRoomCreated(roomId: number): void {
  pendingFocusId.value = roomId
  selectedRoomId.value = roomId
  void load()
}

// ---- ricerca ---------------------------------------------------------------------------------

const searchRoom = ref<number | null>(null)
const searchOptions = ref<{ id: number; label: string }[]>([])

/** Filtra le stanze del grafo per testo (vnum o nome). */
function onSearchFilter(term: string, update: (callback: () => void) => void): void {
  update(() => {
    const needle = term.toLowerCase()
    searchOptions.value = graph.value.nodes
      .map((node) => ({ id: node.id, label: `#${node.vnum} — ${node.name}` }))
      .filter((option) => option.label.toLowerCase().includes(needle))
  })
}

/** Stanza scelta nella ricerca: la seleziona e la centra. */
function onSearchPick(roomId: number | null): void {
  if (roomId === null) {
    highlightedId.value = null
    rebuild()
    return
  }
  selectedEdgeId.value = null
  selectedRoomId.value = roomId
  focusRoom(roomId)
}

watch(
  () => store.selectedZoneId,
  () => {
    searchRoom.value = null
    highlightedId.value = pendingFocusId.value
    clearSelection()
    void load()
  },
)

onMounted(async () => {
  const before = store.selectedZoneId
  await Promise.all([store.loadZones(), store.ensureEnums()])
  // deep-link `?zoneId=` (dalla panoramica, dalla ricerca, dalla lista stanze): seleziona la zona
  const wanted = Number(route.query.zoneId)
  if (route.query.zoneId !== undefined && store.zones.some((zone) => zone.id === wanted)) store.selectedZoneId = wanted
  // se il caricamento delle zone ha cambiato la zona selezionata, ci pensa il watch
  if (store.selectedZoneId === before) await load()
})
</script>

<style lang="scss">
.room-map__panel {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 5;
  width: 260px;
  max-height: calc(100% - 24px);
  overflow-y: auto;
}

.room-map__legend {
  position: absolute;
  bottom: 12px;
  left: 60px;
  z-index: 5;
  max-height: 60%;
  overflow: auto;
}

.room-map__swatch {
  display: inline-block;
  width: 16px;
  height: 16px;
  margin-right: 6px;
  border-radius: 3px;
}
</style>
