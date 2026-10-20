<template>
  <div class="column no-wrap q-px-md q-pt-md" style="height: var(--pachi-page-height, 70vh)">
    <div class="row items-center q-gutter-md q-pb-sm" style="flex: 0 0 auto">
      <h1 class="text-h5 q-ma-none">{{ t('rooms.map.title') }}</h1>
      <q-select
        v-model="store.selectedZoneId"
        :options="zoneOptions"
        option-value="id"
        option-label="label"
        emit-value
        map-options
        :label="t('rooms.zone')"
        style="min-width: 260px"
        dense
        outlined
      />
      <q-btn flat dense :icon="mdiFitToScreen" :label="t('rooms.map.fit')" @click="fitAll" />
      <q-btn flat dense :icon="mdiRefresh" :label="t('rooms.map.reload')" :loading="loading" @click="load" />
      <q-btn flat dense :icon="mdiFormatListBulleted" :label="t('rooms.map.openList')" to="/rooms" />
      <q-space />
      <div class="text-caption text-grey">{{ t('rooms.map.hint') }}</div>
    </div>

    <div class="relative-position" style="flex: 1 1 auto; min-height: 0">
      <VueFlow
        v-if="!loading"
        :nodes="nodes"
        :edges="edges"
        :min-zoom="0.1"
        :max-zoom="2"
        :default-viewport="{ zoom: 0.8 }"
        @nodes-initialized="fitAll"
        @node-click="onNodeClick"
      >
        <template #node-room="nodeProps">
          <room-node v-bind="nodeProps" />
        </template>
        <Background :gap="24" pattern-color="#b0bec5" />
        <Controls position="bottom-left" />
        <MiniMap pannable zoomable />
      </VueFlow>

      <div v-if="!loading && store.selectedZoneId !== null && nodes.length === 0" class="absolute-center text-grey-7">
        {{ t('rooms.map.empty') }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { mdiFitToScreen, mdiFormatListBulleted, mdiRefresh } from '@quasar/extras/mdi-v7'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import type { Edge, Node, NodeMouseEvent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { useFlowControlLabels } from '../../shared/helpers/flow-controls'
import { MiniMap } from '@vue-flow/minimap'
import RoomNode from '../components/RoomNode.vue'
import { getRoomGraph } from '../services/rooms-api'
import { useRoomsStore } from '../stores/use-rooms-store'
import type { DirectionValue } from '../utils/compass'
import { graphToFlow } from '../utils/graph-mapper'
import type { RoomEdgeData, RoomNodeData } from '../utils/graph-mapper'

/**
 * Mappa delle stanze di una zona (grafo vue-flow con layout calcolato dal server). Un clic su
 * una stanza apre l'editor nella lista (`/rooms?zoneId=&roomId=`).
 */
const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const store = useRoomsStore()
const { fitView } = useVueFlow()

const nodes = ref<Node<RoomNodeData>[]>([])
useFlowControlLabels(nodes)
const edges = ref<Edge<RoomEdgeData>[]>([])
const loading = ref(false)
let loadSeq = 0

const zoneOptions = computed(() =>
  store.zones.map((zone) => ({ id: zone.id, label: `${zone.vnum} - ${zone.name}` })),
)

/** Etichetta breve (N, E, S, O, Su, Giù) di una direzione. */
function shortLabel(direction: DirectionValue): string {
  return t(`rooms.map.dir.${direction}`)
}

/** Carica il grafo della zona selezionata. */
async function load(): Promise<void> {
  if (store.selectedZoneId === null) {
    nodes.value = []
    edges.value = []
    return
  }
  // caricamenti sovrapposti (zona di default, poi zona del deep-link): vale solo l'ultimo, altrimenti una risposta in ritardo sovrascrive la mappa
  const ticket = ++loadSeq
  loading.value = true
  try {
    const graph = await getRoomGraph(store.selectedZoneId)
    if (ticket !== loadSeq) return
    const flow = graphToFlow(graph.nodes, graph.edges, shortLabel)
    nodes.value = flow.nodes
    edges.value = flow.edges
  } finally {
    if (ticket === loadSeq) loading.value = false
  }
  await nextTick()
  fitAll()
}

/** Adatta la vista a tutto il grafo. */
function fitAll(): void {
  void fitView({ padding: 0.2 })
}

/** Clic su un nodo: apre l'editor della stanza nella lista. */
function onNodeClick(event: NodeMouseEvent): void {
  void router.push({
    path: '/rooms',
    query: { zoneId: String(store.selectedZoneId), roomId: event.node.id },
  })
}

watch(
  () => store.selectedZoneId,
  () => void load(),
)

onMounted(async () => {
  const before = store.selectedZoneId
  await store.loadZones()
  // deep-link `?zoneId=` (dalla panoramica, dalla ricerca, dalla lista stanze): seleziona la zona
  const wanted = Number(route.query.zoneId)
  if (route.query.zoneId !== undefined && store.zones.some((zone) => zone.id === wanted)) store.selectedZoneId = wanted
  // se il caricamento delle zone ha cambiato la zona selezionata, ci pensa il watch
  if (store.selectedZoneId === before) await load()
})
</script>
